# countedLoop và iteratedLoop

MethodHandles.countedLoop và MethodHandles.iteratedLoop là hai loop combinator được bổ sung trong Java 9. Chúng tạo một MethodHandle mới biểu diễn vòng lặp từ các MethodHandle thành phần: handle khởi tạo, handle xác định số lần lặp hoặc iterator, và handle thân vòng lặp.

Khác với vòng lặp for/foreach thông thường, loop combinator mô tả luồng điều khiển bằng các MethodHandle có kiểu cụ thể. Cách này hữu ích khi xây dựng bộ kết hợp MethodHandle, adapter hoặc một pipeline mà phần thân và nguồn dữ liệu được chọn động. Với logic cố định trong code ứng dụng, vòng lặp Java thông thường thường dễ đọc và dễ bảo trì hơn.

## 1. Tổng quan hai combinator

Hai phương thức chính có từ Java 9:

~~~java
static MethodHandle countedLoop(
        MethodHandle iterations,
        MethodHandle init,
        MethodHandle body
)

static MethodHandle iteratedLoop(
        MethodHandle iterator,
        MethodHandle init,
        MethodHandle body
)
~~~

**countedLoop** chạy theo số lần lặp được xác định bởi một MethodHandle trả về int. Counter bắt đầu từ 0 và tăng 1 sau mỗi vòng.

**iteratedLoop** duyệt các phần tử do một Iterator cung cấp. Nếu iterator handle là null, combinator dùng Iterable.iterator() trên đối số Iterable đầu vào.

Cả hai có thể duy trì một accumulator: giá trị được khởi tạo một lần, truyền vào body ở mỗi vòng, cập nhật bằng giá trị body trả về và được trả lại khi vòng lặp kết thúc.

## 2. MethodHandle và chữ ký là hợp đồng của vòng lặp

Các handle truyền vào phải có chữ ký tương thích. Có thể xem chữ ký theo dạng:

~~~text
(returnType) (parameterTypes...)
~~~

Ví dụ một body nhận accumulator String và counter int rồi trả về String có kiểu:

~~~text
(String, int)String
~~~

MethodHandles.countedLoop không nhận một lambda bất kỳ rồi tự suy ra mọi kiểu. Nó kiểm tra MethodType của các handle để xác định cách nối chúng. Nếu chữ ký không tương thích, việc tạo loop handle có thể ném IllegalArgumentException.

Khi tạo handle bằng Lookup.findStatic, findVirtual hoặc các factory khác, hãy khai báo MethodType đúng với method đích:

~~~java
MethodType.methodType(
        String.class,
        String.class,
        int.class
)
~~~

Trong đó đối số đầu là kiểu trả về; các đối số tiếp theo là kiểu tham số theo thứ tự.

## 3. countedLoop với số lần lặp

Overload ba tham số:

~~~java
MethodHandles.countedLoop(iterations, init, body)
~~~

Có ba handle:

- **iterations**: bắt buộc, trả về int và xác định số lần lặp.
- **init**: tùy chọn, khởi tạo accumulator nếu body trả về một giá trị khác void.
- **body**: bắt buộc, chạy một lần trong mỗi vòng.

Với accumulator kiểu V và các tham số bên ngoài A..., chữ ký tổng quát là:

~~~text
iterations: (A...)int
init:       (A...)V
body:       (V, int, A...)V
result:     (A...)V
~~~

Body nhận accumulator hiện tại trước, counter zero-based sau đó, rồi đến các tham số bên ngoài. Giá trị body trả về trở thành accumulator cho vòng kế tiếp.

Ví dụ logic tương đương:

~~~java
V value = init(args);
int count = iterations(args);

for (int i = 0; i < count; i++) {
    value = body(value, i, args);
}

return value;
~~~

Đây là pseudocode mô tả luồng thực thi. MethodHandle thật được gọi theo MethodType, không phải bằng cách gọi trực tiếp các biến Java trong pseudocode.

Nếu body trả về void, không có accumulator:

~~~text
body:   (int, A...)void
result: (A...)void
~~~

Trong trường hợp này body chỉ nhận counter và các tham số bên ngoài.

Nếu iterations trả về 0 hoặc số âm, điều kiện i < count không đúng ngay từ đầu nên body không chạy. Với body có accumulator, initializer vẫn cung cấp giá trị kết quả ban đầu.

## 4. countedLoop với khoảng start/end

Java 9 còn có overload bốn tham số:

~~~java
MethodHandles.countedLoop(start, end, init, body)
~~~

Hai handle start và end đều trả về int. Counter chạy từ start, bao gồm start, đến end nhưng không bao gồm end. Bước tăng luôn là 1.

Chữ ký tổng quát:

~~~text
start: (A...)int
end:   (A...)int
init:  (A...)V
body:  (V, int, A...)V
result:(A...)V
~~~

Ví dụ với start = 2 và end = 5, body nhận lần lượt các counter 2, 3, 4. Khi start lớn hơn hoặc bằng end, body không được gọi; accumulator vẫn là giá trị init.

Overload này hữu ích khi cần biểu diễn một đoạn chỉ số mà không phải tự trừ start khỏi counter. Nếu cần bước nhảy khác 1, điều kiện dừng phức tạp hoặc cập nhật nhiều biến trạng thái, có thể dùng loop combinator tổng quát khác hoặc viết vòng lặp Java thông thường.

## 5. iteratedLoop duyệt Iterator

Overload:

~~~java
MethodHandles.iteratedLoop(iterator, init, body)
~~~

Các thành phần:

- **iterator**: tùy chọn, là MethodHandle trả về Iterator hoặc subtype.
- **init**: tùy chọn, khởi tạo accumulator nếu body trả về giá trị.
- **body**: bắt buộc, nhận từng phần tử iterator và cập nhật accumulator hoặc thực hiện tác vụ void.

Với accumulator V, phần tử T và tham số bên ngoài A..., dạng chữ ký là:

~~~text
iterator: (A...)Iterator
init:     (A...)V
body:     (V, T, A...)V
result:   (A...)V
~~~

Nếu body trả về void:

~~~text
body:   (T, A...)void
result: (A...)void
~~~

Khi iterator handle là null, combinator sử dụng hành vi tương đương Iterable.iterator() trên đối số Iterable đầu vào. Trong trường hợp phổ biến body chỉ nhận accumulator và phần tử, loop handle được gọi với một Iterable.

Pseudocode:

~~~java
Iterator<T> it = iterator(input);
V value = init(input);

while (it.hasNext()) {
    T item = it.next();
    value = body(value, item, input);
}

return value;
~~~

Nếu iterator rỗng, body không chạy và loop trả về giá trị init. Nếu không có accumulator vì body trả về void, loop chỉ duyệt và thực hiện body cho từng phần tử.

## 6. Cách chọn iterator handle

Có hai cách phổ biến:

**Để iterator là null**

Dùng khi đầu vào của loop là Iterable và muốn combinator tự gọi iterator():

~~~java
MethodHandle loop = MethodHandles.iteratedLoop(
        null,
        init,
        body
);
~~~

Với body có dạng (V,T)V và init không có tham số, loop handle nhận Iterable làm đối số.

**Cung cấp iterator handle**

Dùng khi cần lấy Iterator từ một đối tượng hoặc tham số theo cách riêng:

~~~java
MethodHandle iterator = lookup.findVirtual(
        Iterable.class,
        "iterator",
        MethodType.methodType(Iterator.class)
);
~~~

Iterator handle phải trả về Iterator hoặc subtype. Các tham số của iterator handle góp phần xác định tham số bên ngoài của loop handle; init và body phải tương thích với danh sách đó.

Không tạo iterator mới ở mỗi lần gọi body. Iterator được lấy để bắt đầu vòng lặp, sau đó được tiêu thụ tuần tự qua hasNext() và next().

## 7. Accumulator và body void

Accumulator hữu ích khi mỗi vòng cần tạo ra một kết quả tổng hợp:

- countedLoop: cộng dồn tổng, tạo chuỗi, cập nhật trạng thái.
- iteratedLoop: gom phần tử, tính thống kê, xây dựng kết quả từ Iterable.

Body phải trả về đúng kiểu accumulator. Ví dụ nếu init trả về StringBuilder thì body cũng phải trả về StringBuilder.

Nếu body trả về void, loop không có accumulator và kết quả của loop handle cũng là void. Trường hợp này phù hợp khi mỗi phần tử chỉ gây ra một hành động, ví dụ ghi log hoặc cập nhật một đối tượng có sẵn.

Đừng khai báo init trả về một kiểu rồi viết body trả về kiểu khác. Kiểu trả về của body xác định kiểu accumulator V; init phải tương thích với V.

## 8. Tham số bên ngoài được truyền qua mỗi vòng

Các loop combinator có thể nhận thêm tham số bên ngoài A... ngoài accumulator và counter/element. Những tham số này thường là dữ liệu bất biến trong suốt một lần chạy loop, ví dụ:

- Prefix cần thêm vào từng chuỗi.
- Ngưỡng so sánh.
- Một cấu hình hoặc context.
- Đối tượng đích được cập nhật.

Với countedLoop, iterations và init có thể nhận các tham số ngoài; body nhận accumulator, counter và các tham số đó.

Với iteratedLoop, iterator handle có thể nhận tham số để tạo Iterator; init và body phải có chữ ký tương thích với tham số ngoài. Khi iterator là null, Iterable đầu vào đóng vai trò nguồn duyệt theo quy tắc của combinator.

Chỉ những tham số được khai báo trong MethodType mới có thể được truyền vào loop handle. Không thể tùy ý thêm một đối số vào lúc invoke nếu loop handle không có parameter tương ứng.

## 9. Kiểm tra MethodType và invoke

Mọi MethodHandle có MethodType:

~~~java
MethodType type = loop.type();
System.out.println(type);
~~~

Điều này giúp xác nhận kiểu đầu vào và đầu ra của loop sau khi kết hợp. Nó đặc biệt hữu ích khi các handle được tạo động hoặc ghép từ nhiều nguồn.

Có hai cách gọi thường gặp:

- **invokeExact** yêu cầu kiểu tại call site khớp chính xác với MethodType của handle.
- **invoke** cho phép các chuyển đổi kiểu mà MethodHandle.asType hỗ trợ, nhưng không tự chuyển đổi mọi kiểu tùy ý.

Nếu kiểu không khớp, có thể gặp WrongMethodTypeException. Nếu các thành phần không thỏa ràng buộc khi tạo combinator, MethodHandles.countedLoop hoặc iteratedLoop có thể ném IllegalArgumentException.

Khi debug, in type() của từng handle thành phần và của loop cuối cùng. Đây thường là cách nhanh nhất để tìm lỗi sai thứ tự tham số hoặc sai kiểu trả về.

## 10. Ví dụ chạy được với Java 17+

Tạo file **MethodHandleLoopDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;
import java.util.List;

public class MethodHandleLoopDemo {
    static int fourIterations() {
        return 4;
    }

    static String emptyText() {
        return "";
    }

    static String appendIndex(String value, int index) {
        return value + (index + 1);
    }

    static int addIndex(int sum, int index) {
        return sum + index;
    }

    static StringBuilder newText() {
        return new StringBuilder();
    }

    static StringBuilder appendWord(StringBuilder result, String word) {
        if (result.length() > 0) {
            result.append(", ");
        }
        return result.append(word);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle iterations = lookup.findStatic(
                MethodHandleLoopDemo.class,
                "fourIterations",
                MethodType.methodType(int.class)
        );
        MethodHandle initText = lookup.findStatic(
                MethodHandleLoopDemo.class,
                "emptyText",
                MethodType.methodType(String.class)
        );
        MethodHandle append = lookup.findStatic(
                MethodHandleLoopDemo.class,
                "appendIndex",
                MethodType.methodType(
                        String.class,
                        String.class,
                        int.class
                )
        );

        MethodHandle counted = MethodHandles.countedLoop(
                iterations,
                initText,
                append
        );
        String countedResult = (String) counted.invokeExact();
        System.out.println("countedLoop: " + countedResult);

        MethodHandle start = MethodHandles.constant(int.class, 2);
        MethodHandle end = MethodHandles.constant(int.class, 5);
        MethodHandle initSum = MethodHandles.constant(int.class, 0);
        MethodHandle add = lookup.findStatic(
                MethodHandleLoopDemo.class,
                "addIndex",
                MethodType.methodType(int.class, int.class, int.class)
        );
        MethodHandle range = MethodHandles.countedLoop(
                start,
                end,
                initSum,
                add
        );
        int rangeSum = (int) range.invokeExact();
        System.out.println("countedLoop range sum: " + rangeSum);

        MethodHandle initBuilder = lookup.findStatic(
                MethodHandleLoopDemo.class,
                "newText",
                MethodType.methodType(StringBuilder.class)
        );
        MethodHandle appendWord = lookup.findStatic(
                MethodHandleLoopDemo.class,
                "appendWord",
                MethodType.methodType(
                        StringBuilder.class,
                        StringBuilder.class,
                        String.class
                )
        );
        MethodHandle iterated = MethodHandles.iteratedLoop(
                null,
                initBuilder,
                appendWord
        );
        List<String> words = Arrays.asList("red", "green", "blue");
        StringBuilder iteratedResult =
                (StringBuilder) iterated.invoke((Iterable<String>) words);
        System.out.println("iteratedLoop: " + iteratedResult);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MethodHandleLoopDemo.java
java MethodHandleLoopDemo
~~~

Kết quả stdout:

~~~text
countedLoop: 1234
countedLoop range sum: 9
iteratedLoop: red, green, blue
~~~

Ví dụ đầu tiên dùng countedLoop với bốn vòng, counter từ 0 đến 3; body nối index + 1 vào accumulator String.

Ví dụ thứ hai dùng overload start/end. Counter chạy 2, 3, 4 nên tổng accumulator bằng 9.

Ví dụ thứ ba dùng iteratedLoop với iterator là null. Combinator lấy iterator từ Iterable words và nối từng phần tử theo thứ tự nguồn.

Ví dụ được biên dịch bằng API Java 9 với javac --release 9 và chạy trên JDK 24.0.2.

## 11. Lỗi thường gặp

**Sai thứ tự tham số của body:** countedLoop truyền accumulator trước counter; iteratedLoop truyền accumulator trước phần tử. Đối chiếu MethodType thay vì đoán.

**Body trả về sai kiểu:** nếu body tạo accumulator V thì kiểu trả về phải đúng V và init phải tạo được V.

**Iterations handle không trả về int:** countedLoop yêu cầu kiểu trả về int; kiểu khác làm chữ ký không hợp lệ.

**Iterator handle không trả về Iterator:** iteratedLoop yêu cầu Iterator hoặc subtype. Nếu để null, đầu vào phải thỏa hợp đồng Iterable mặc định.

**Nhầm end là inclusive:** overload start/end chạy đến end nhưng không bao gồm end.

**Dùng iterator đã tiêu thụ:** mỗi lần loop cần iterator phù hợp với lần duyệt mới. Nếu dùng lại một Iterator đã ở cuối, body có thể không chạy.

**Quên type erasure:** Iterator<T> bị xóa kiểu generic ở runtime. Chuyển đổi sang kiểu T có thể phát sinh ClassCastException hoặc lỗi unboxing nếu phần tử không đúng kiểu mong đợi.

**Nhầm invoke với invokeExact:** invokeExact cần call-site descriptor chính xác; invoke chỉ hỗ trợ các chuyển đổi theo quy tắc MethodHandle.

**Dùng loop combinator cho mọi vòng lặp:** combinator tăng độ phức tạp chữ ký và debugging. Với vòng lặp nghiệp vụ cố định, for/foreach thường rõ ràng hơn.

## 12. Khi nào nên dùng?

Dùng countedLoop khi số vòng được cung cấp động dưới dạng MethodHandle hoặc khi cần đóng gói một vòng đếm thành một MethodHandle để ghép tiếp với combinator khác.

Dùng overload start/end khi cần duyệt một đoạn int với điểm đầu inclusive và điểm cuối exclusive.

Dùng iteratedLoop khi nguồn dữ liệu là Iterator/Iterable được xác định động hoặc khi muốn biểu diễn phép biến đổi theo từng phần tử dưới dạng MethodHandle.

Dùng loop combinator tổng quát MethodHandles.loop khi cần nhiều loop variable, nhiều điều kiện kết thúc hoặc cấu trúc vòng lặp phức tạp hơn các wrapper countedLoop/iteratedLoop.

Không chọn combinator chỉ vì nó mới hoặc có vẻ nhanh hơn. Đo hiệu năng trên workload thực tế và ưu tiên cấu trúc dễ đọc, dễ kiểm thử.

## 13. Checklist thiết kế

- Chọn countedLoop cho số vòng hoặc khoảng chỉ số; chọn iteratedLoop cho Iterator.
- Khai báo chính xác MethodType của iterations, iterator, init và body.
- Kiểm tra body có accumulator hay trả về void.
- Với accumulator, bảo đảm init và body dùng cùng kiểu V.
- Nhớ counter của countedLoop bắt đầu từ 0 hoặc start và end là exclusive.
- Với iteratedLoop(null, ...), cung cấp Iterable đúng kiểu.
- Kiểm tra type() của loop handle trước khi invoke khi ghép động.
- Dùng invokeExact khi call site có descriptor khớp chính xác; dùng invoke khi cần các chuyển đổi được hỗ trợ.
- Xử lý exception từ init, iterator hoặc body ở tầng gọi.
- Dùng vòng lặp Java thông thường nếu đó là cách diễn đạt đơn giản nhất.

## Tài liệu tham khảo

- [MethodHandles — Java SE 24 API: countedLoop](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.html#countedLoop(java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle))
- [MethodHandles — Java SE 24 API: iteratedLoop](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.html#iteratedLoop(java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle,java.lang.invoke.MethodHandle))
- [MethodHandle — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandle.html)
