var primeiroValor = parseInt(prompt("Digite o primeiro valor: "))
var segundoValor = parseInt(prompt("Digite o segundo valor: "))

var operacao = prompt("1 para dividir, 2 para multiplicar, 3 para somar e 4 para subtrair ")

if (operacao == 1){
var resultado = primeiroValor / segundoValor
document.write("<h2>" + primeiroValor + " / " + segundoValor + " = " + resultado + "</h2>")
}
else if (operacao == 2){
  var resultado = primeiroValor * segundoValor
  document.write("<h2>" + primeiroValor + " * " + segundoValor + " = " + resultado + "</h2>")
}
else if (operacao == 3){
  var resultado = primeiroValor + segundoValor
  document.write("<h2>" + primeiroValor + " + " + segundoValor + " = " + resultado + "</h2>")
}
else if (operacao == 4){
  var resultado = primeiroValor - segundoValor
  document.write("<h2>" + primeiroValor + " - " + segundoValor + " = " + resultado + "</h2>")
}
else {
  document.write("<h2> Opção Inválida. Escolha entre as opções disponívéis, de 1 a 4. </h2>")
}
