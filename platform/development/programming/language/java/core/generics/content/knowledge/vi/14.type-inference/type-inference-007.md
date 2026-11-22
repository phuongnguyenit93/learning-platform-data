# Poly expression, lời gọi lồng nhau và giới hạn lan truyền kiểu đích trong Java Generics

## 1. Đọc đúng vấn đề

Khi sử dụng generics, Java có thể suy luận tham số kiểu nhờ **ngữ cảnh** nơi một biểu thức xuất hiện. Chẳng hạn:

~~~java
List<String> names = Collections.emptyList();
~~~

Phương thức Collections.emptyList() có khai báo đại ý là **static <T> List<T> emptyList()**. Nó không nhận đối số, nhưng trong phép gán trên, Java vẫn suy luận được T là String nhờ kiểu đích **List<String>**.

Khả năng này gắn với **poly expression**: biểu thức có kiểu phụ thuộc vào ngữ cảnh thích hợp, chứ không chỉ được quyết định độc lập từ nội dung bên trong biểu thức.

Câu hỏi khó hơn xuất hiện khi có lời gọi lồng nhau:

~~~java
List<String> a = identity(Collections.emptyList());
List<String> b = Collections.emptyList().stream().toList();
~~~

Hai biểu thức nhìn có vẻ đều bắt đầu từ emptyList(), nhưng câu đầu có thể biên dịch còn câu thứ hai **không biên dịch**. Ta phải xét **vị trí cú pháp của từng lời gọi**, loại ngữ cảnh cung cấp kiểu đích và cách ràng buộc kiểu đi qua các phương thức. Đây là giới hạn thực tế quan trọng nhất của suy luận kiểu lồng nhau.

Các ví dụ trong bài sử dụng Java 17+ và những API tiêu chuẩn thuộc java.util, java.util.function và java.util.stream.

## 2. Ba khái niệm nền tảng: target type, standalone expression và poly expression

**Target type (kiểu đích)** là kiểu mà ngữ cảnh mong muốn biểu thức tạo ra. Các nguồn kiểu đích thường gặp gồm:

- **Phép gán / khai báo có kiểu tường minh**: List<String> x = Collections.emptyList();.
- **Đối số lời gọi phương thức**: consume(Collections.emptyList()); khi consume nhận List<String>.
- **Biểu thức trả về từ phương thức**: phương thức khai báo trả về List<String>, rồi return Collections.emptyList();.
- **Ép kiểu tường minh** và một số ngữ cảnh khác được đặc tả.
- **Các nhánh của biểu thức điều kiện dạng tham chiếu** khi bản thân biểu thức điều kiện là poly expression.

**Standalone expression** là biểu thức có kiểu được xác định chủ yếu từ chính biểu thức và ngữ cảnh riêng của nó, thay vì được áp kiểu mong muốn từ phép gán bên ngoài theo cơ chế poly expression.

**Poly expression** là biểu thức được Java Language Specification quy định là nhận kiểu đích ở những ngữ cảnh nhất định. Không phải cứ nằm trong câu lệnh gán là mọi biểu thức con đều nhận cùng một kiểu đích.

Ví dụ:

~~~java
List<String> one = Collections.emptyList(); // Kiểu đích giúp suy ra T = String.
var two = Collections.emptyList();          // List<Object>: không có target String.
~~~

Với khai báo thứ hai, **var không phải kiểu đích String**. Tại lời gọi emptyList() không có ràng buộc cụ thể, T được suy luận thành Object và kiểu tĩnh của two là List<Object>. Việc dùng two ở các dòng sau không sửa kết quả đã suy luận.

### Poly expression không đồng nghĩa generic expression

Không phải biểu thức có generic là poly trong mọi vị trí. Đối với **method invocation** generic, các điều kiện chính gồm lời gọi xuất hiện trong **assignment context** hoặc **invocation context**, sử dụng tham số kiểu liên quan tới kiểu trả về, và thuộc dạng được JLS cho phép xét kiểu đích. Lời gọi đó nằm ở vị trí receiver của một lời gọi tiếp theo không tự động nhận target type từ phép gán ở ngoài.

Các dạng poly expression phổ biến khác gồm lambda expression, method reference, lời gọi constructor dùng diamond trong ngữ cảnh phù hợp, một số conditional expression tham chiếu và switch expression tham chiếu. Mỗi dạng có quy tắc riêng. Ta không thể kết luận rằng mọi biểu thức nằm bên trong một poly expression đều là poly expression.

## 3. Suy luận kiểu generic tại một lời gọi phương thức

Xét phương thức generic tự viết:

~~~java
static <T> T identity(T value) {
    return value;
}
~~~

Tham số kiểu T xuất hiện cả ở đối số đầu vào lẫn kiểu trả về. Vì thế compiler có thể nhận ràng buộc từ **đối số thực tế**, **kiểu đích của toàn lời gọi**, hoặc cả hai để tìm một kiểu thỏa mãn.

~~~java
String s = identity("Java");                  // T = String nhờ đối số "Java".
List<String> x = identity(Collections.emptyList());
~~~

Ở dòng x:

1. Kiểu đích của phép gán là List<String>.
2. identity(...) là lời gọi generic phù hợp để xét theo assignment context.
3. Ràng buộc từ kiểu trả về T của identity gắn với List<String>.
4. Lời gọi Collections.emptyList() bên trong được xét như đối số của identity, với ràng buộc từ tham số hình thức T.
5. Bộ giải ràng buộc generic phối hợp thông tin của lời gọi bên ngoài và lời gọi bên trong; kết quả hợp lệ là List<String>.

Vì vậy, có thể nói **thông tin kiểu đích được truyền qua suy luận lời gọi lồng nhau** trong trường hợp này. Tuy nhiên, đây không phải thao tác sao chép target type cơ học từ ngoài vào mọi biểu thức con. Compiler giải hệ ràng buộc theo các quy tắc suy luận kiểu của Java; khác biệt của vị trí cú pháp và kiểu formal parameter có thể thay đổi kết quả.

### Kiểu đích từ đối số phương thức

Giả sử có:

~~~java
static void consume(List<String> names) {
    System.out.println(names);
}
~~~

Hai lời gọi sau đều hợp lệ:

~~~java
consume(Collections.emptyList());
consume(identity(Collections.emptyList()));
~~~

Đối số của consume xuất hiện trong **invocation context** yêu cầu List<String>. Ở trường hợp lồng nhau, suy luận có thể phối hợp các ràng buộc qua identity và emptyList.

Ngược lại:

~~~java
var temp = Collections.emptyList(); // temp là List<Object>.
// consume(temp);                   // Lỗi biên dịch.
~~~

**Biến trung gian đã được gán kiểu** là một ranh giới quan trọng. Khi temp được suy luận thành List<Object>, một lời gọi consume ở phía sau không thể quay ngược lại để làm temp đổi thành List<String>.

### Kiểu đích từ return

Nếu phương thức đang định nghĩa có kiểu trả về List<String> thì biểu thức return cũng có ngữ cảnh kiểu đích:

~~~java
static List<String> makeNames() {
    return identity(Collections.emptyList());
}
~~~

Dòng return hợp lệ vì hệ ràng buộc có thể suy luận các lời gọi generic về kiểu phù hợp với List<String>. Đặt cùng một initializer vào biến var trước khi return sẽ đổi tình huống:

~~~java
static List<String> brokenExample() {
    var intermediate = Collections.emptyList(); // List<Object>.
    // return intermediate;                      // Không biên dịch.
    return Collections.emptyList();              // Hợp lệ.
}
~~~

Bản thân từ khóa return không thay đổi kiểu của biến đã khai báo.

## 4. Khi nào kiểu đích không lan truyền xuyên qua lời gọi lồng nhau?

Đây là điểm dễ sai nhất. So sánh hai trường hợp:

~~~java
List<String> valid = Collections.emptyList();
List<String> invalid = Collections.emptyList().stream().toList(); // Lỗi.
~~~

Ở dòng valid, emptyList() là **toàn bộ biểu thức phía phải** của phép gán nên nhận kiểu đích List<String>.

Ở dòng invalid, emptyList() làm **receiver** của lời gọi .stream(). Phần **Collections.emptyList()** không xuất hiện trực tiếp trong assignment context hoặc invocation context của biểu thức gán cho List<String>. Nó được xác định kiểu trước tại vị trí receiver, nơi không có ràng buộc buộc T là String. Vì không có đối số kiểu cụ thể, nó được suy luận thành List<Object>. Sau đó:

~~~text
Collections.emptyList()      → List<Object>
             .stream()       → Stream<Object>
             .toList()       → List<Object>
Gán cho List<String>         → Lỗi biên dịch
~~~

Mặc dù toàn biểu thức đứng bên phải List<String>, compiler **không truyền mục tiêu String ngược xuyên qua chuỗi gọi phương thức để sửa kiểu của receiver đã xác định**.

### Cách giải quyết ranh giới receiver

Cung cấp kiểu trước khi bắt đầu chuỗi:

~~~java
List<String> good = Collections.<String>emptyList()
        .stream()
        .toList();
~~~

Cụm **Collections.<String>emptyList()** là lời gọi phương thức generic có **type witness** <String>. Nó buộc T là String tại chính vị trí tạo receiver. Khi đó stream() trả về Stream<String> và toList() trả về List<String>.

Tương tự, với Stream.empty():

~~~java
List<String> bad = java.util.stream.Stream.empty().toList(); // Lỗi.
List<String> good = java.util.stream.Stream.<String>empty().toList();
~~~

Stream.empty() ở vị trí receiver của toList(), nên mặc định là Stream<Object> khi không có ràng buộc khác. Stream.<String>empty() khắc phục bằng việc chỉ rõ kiểu trước khi nối chuỗi.

**Quy tắc kiểm tra hữu ích:** hãy xác định biểu thức nào làm receiver tại từng dấu chấm. Nếu receiver là một lời gọi generic không có đối số mang thông tin kiểu, target type của phép gán ngoài cùng thường không đủ để định kiểu lại receiver đó.

## 5. Diamond trong lời gọi lồng nhau: theo dõi đúng ranh giới

Constructor dùng diamond nhận thông tin từ target type và từ các đối số được truyền vào:

```java
List<String> a = new ArrayList<>();
List<String> b = new ArrayList<>(Collections.emptyList());
var c = new ArrayList<>();                // ArrayList<Object>.
var d = new ArrayList<>(List.of("Java")); // ArrayList<String>.
```

Dòng `b` là một **lời gọi constructor có target** `List<String>`; ràng buộc E từ `ArrayList<E>` phối hợp với generic call `Collections.emptyList()` làm đối số constructor. Dòng `c` thiếu cả target String lẫn đối số xác định E; dòng `d` nhận thông tin String từ chính constructor argument.

Khác với **chuỗi receiver** ở mục 4, lời gọi generic bên trong constructor là **đối số**, nên có cơ hội tham gia inference qua invocation context. Nhưng nếu gán trước `var source = Collections.emptyList()`, kiểu `List<Object>` của biến đó đã chốt; `new ArrayList<>(source)` không tự biến nó thành `List<String>`.

Phân biệt hai ranh giới: *constructor argument có thể nhận thông tin ngữ cảnh*; *một generic method call đã trở thành receiver của method chain không nhất thiết nhận target ngoài cùng*. Đây là lý do bài này phân tích vị trí biểu thức, thay vì chỉ lặp lại hướng dẫn dùng diamond.

## 6. Lambda và method reference: poly expression cần kiểu đích

Khác biệt rất rõ khi dùng functional interface:

~~~java
Function<String, Integer> length = s -> s.length();
~~~

Biểu thức lambda **s -> s.length()** nhận kiểu đích Function<String, Integer>; compiler biết tham số s là String nên có thể tra cứu phương thức length().

Lệnh sau không biên dịch:

~~~java
var length = s -> s.length(); // Lỗi: lambda expression needs an explicit target-type.
~~~

Lý do không phải var bị cấm trong mọi khai báo liên quan lambda: lambda **cần target type là một functional interface**, còn var không tự suy ra functional interface mong muốn chỉ từ thân lambda. Một lambda có thể phù hợp với nhiều giao diện khác nhau.

Method reference tương tự:

~~~java
Supplier<List<String>> factory = Collections::emptyList;
Function<String, Integer> length = String::length;
~~~

Hai biến trên có target functional interface rõ ràng, nên compiler biết kiểu phương thức cần ghép.

~~~java
var factory = Collections::emptyList; // Lỗi: method reference cần target type.
~~~

Dùng var với **kết quả của một lời gọi phương thức trả về functional interface** thì khác; lúc đó initializer đã có kiểu riêng. Ví dụ:

~~~java
static java.util.function.Function<String, Integer> createLengthFunction() {
    return String::length;
}

var lengthFunction = createLengthFunction(); // Hợp lệ.
~~~

Ở đây var suy luận từ kiểu trả về Function<String, Integer> của createLengthFunction(), chứ không suy luận trực tiếp từ method reference.

## 7. Conditional expression và giới hạn của kiểu đích

Một biểu thức điều kiện kiểu tham chiếu có thể là poly expression khi xuất hiện trong ngữ cảnh phù hợp:

~~~java
List<String> chosen = flag
        ? Collections.emptyList()
        : List.of("fallback");
~~~

Trong một chương trình nơi flag là boolean đã khai báo, phép gán có target List<String>. Thông tin đó có thể dùng để kiểm tra hai nhánh, bao gồm suy luận emptyList() thành List<String>. Kiểu đích được phân phối theo quy tắc của **reference conditional expression**.

Nhưng không nên suy ra rằng mọi biểu thức toán tử đều lan truyền kiểu theo cơ chế này. Ví dụ số học, biểu thức điều kiện có nhánh primitive, lời gọi method chain, và lambda đều có quy tắc riêng; phép gán bên ngoài không làm tất cả biểu thức con thành poly một cách mặc định.

Đặc biệt:

~~~java
var chosen = flag
        ? Collections.emptyList()
        : List.of("fallback");
~~~

Không có target List<String> do vế trái cung cấp. Compiler phải tìm kiểu của conditional expression theo quy tắc áp dụng khi không có ngữ cảnh đích cụ thể; đừng giả định chosen chắc chắn có kiểu List<String> chỉ vì một nhánh chứa chuỗi.

## 8. Chương trình Java 17+ chạy được

Lưu mã sau thành **PolyTargetDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Function;
import java.util.function.Supplier;

public class PolyTargetDemo {
    static <T> T identity(T input) {
        return input;
    }

    static void consume(List<String> names) {
        System.out.println("consume=" + names);
    }

    static List<String> fromReturn() {
        return identity(Collections.emptyList());
    }

    public static void main(String[] args) {
        List<String> direct = Collections.emptyList();

        // Target type phối hợp với lời gọi generic lồng nhau.
        List<String> nested = identity(Collections.emptyList());
        consume(identity(Collections.emptyList()));

        // Diamond và lời gọi generic bên trong cùng được suy luận.
        List<String> constructed =
                new ArrayList<>(Collections.emptyList());

        // Type witness khắc phục ranh giới receiver trong method chain.
        List<String> chained = Collections.<String>emptyList()
                .stream()
                .toList();

        // Lambda và method reference nhận kiểu từ functional interface.
        Supplier<List<String>> factory = Collections::emptyList;
        Function<String, Integer> length = String::length;

        // Reference conditional expression nhận target List<String>.
        List<String> selected = true
                ? Collections.emptyList()
                : List.of("fallback");

        // Dù dùng var, đối số constructor đã cho thông tin kiểu.
        var inferred = new ArrayList<>(List.of("A", "B"));

        System.out.println("direct=" + direct);
        System.out.println("nested=" + nested);
        System.out.println("constructed=" + constructed);
        System.out.println("chained=" + chained);
        System.out.println("factory=" + factory.get());
        System.out.println("length=" + length.apply("Java"));
        System.out.println("selected=" + selected);
        System.out.println("inferred=" + inferred);
        System.out.println("fromReturn=" + fromReturn());
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac PolyTargetDemo.java
java PolyTargetDemo
~~~

Stdout chính xác:

~~~text
consume=[]
direct=[]
nested=[]
constructed=[]
chained=[]
factory=[]
length=4
selected=[]
inferred=[A, B]
fromReturn=[]
~~~

**Vì sao selected là danh sách rỗng?** Điều kiện true chọn nhánh Collections.emptyList(). Nhánh còn lại List.of("fallback") vẫn hợp lệ về kiểu nhưng không chạy. Hàm length.apply("Java") trả về 4 vì String "Java" có bốn ký tự.

Đối với mã thử nghiệm có dòng static <T> T identity(T input), target type phía ngoài có thể ràng buộc T và lời gọi inner emptyList(). Với dòng chained, việc viết type witness trực tiếp tại emptyList() đảm bảo receiver có kiểu List<String> trước khi gọi stream().

## 9. Những đoạn cố ý không biên dịch và cách sửa

Các ví dụ dưới đây là **mảnh mã độc lập để nhận diện lỗi**, không được chèn nguyên vào chương trình PolyTargetDemo.java.

### Sai A: target type không đi ngược qua receiver

~~~java
List<String> x = Collections.emptyList().stream().toList(); // Không biên dịch.
~~~

Lý do: lời gọi emptyList() ở vị trí receiver được suy luận List<Object>; sau đó toList() cho List<Object>, không thể gán cho List<String>.

~~~java
List<String> x = Collections.<String>emptyList().stream().toList();
~~~

Sửa bằng type witness ở lời gọi cần ràng buộc kiểu, trước chuỗi stream().

### Sai B: kỳ vọng biến trung gian thay đổi kiểu hồi tố

~~~java
var values = Collections.emptyList(); // List<Object>.
List<String> names = values;          // Không biên dịch.
~~~

Lý do: suy luận kiểu hoàn tất ở dòng khai báo values. Generic trong Java là invariant, nên List<Object> không thể tự chuyển thành List<String>.

~~~java
List<String> values = Collections.emptyList();
List<String> names = values;
~~~

Sửa bằng cách cung cấp kiểu đích ngay ở nơi tạo biến values.

### Sai C: dùng var trực tiếp với lambda/method reference

~~~java
var mapper = (String s) -> s.length(); // Không biên dịch.
var supplier = Collections::emptyList; // Không biên dịch.
~~~

Sửa bằng cách khai báo functional interface cụ thể:

~~~java
Function<String, Integer> mapper = s -> s.length();
Supplier<List<String>> supplier = Collections::emptyList;
~~~

### Sai D: nghĩ mọi nested method invocation đều nhận một target type duy nhất

So sánh:

~~~java
List<String> works = identity(Collections.emptyList());
List<String> fails = Collections.emptyList().stream().toList();
~~~

Lệnh thứ nhất có liên kết ràng buộc generic từ identity đến đối số emptyList(); lệnh thứ hai có **receiver boundary** nên không được suy luận cùng cách. “Lồng nhau” chỉ mô tả hình thức cú pháp; **vị trí lồng nhau** mới quyết định ngữ cảnh kiểu.

### Sai E: tưởng Object là raw type hoặc kiểu động

~~~java
var source = Collections.emptyList(); // List<Object>, có generic cụ thể.
~~~

List<Object> khác với raw List và List<?>:

- **List<Object>** cho phép thêm Object và các subtype nếu danh sách có thể sửa đổi.
- **Raw List** bỏ qua thông tin tham số generic và có thể dẫn tới cảnh báo unchecked.
- **List<?>** là danh sách có kiểu phần tử chưa biết, không thể tự do thêm giá trị khác null.

Tuy nhiên, riêng Collections.emptyList() trả về **danh sách rỗng không thể thay đổi**. Việc suy luận thành List<Object> không có nghĩa là gọi add sẽ thành công khi chạy. Mã đúng kiểu vẫn có thể ném UnsupportedOperationException nếu collection không hỗ trợ thay đổi.

## 10. Quy trình tự phân tích một biểu thức generic phức tạp

Khi không hiểu vì sao compiler chọn Object, String hoặc báo incompatible types, hãy đi theo các bước sau:

1. **Khoanh toàn bộ biểu thức được gán/trả về/truyền làm đối số** và ghi kiểu đích dự kiến nếu có.
2. **Tìm các generic method invocation**: xem khai báo phương thức, tham số kiểu, kiểu trả về và các tham số hình thức.
3. **Xác định ngữ cảnh của từng lời gọi cụ thể**: assignment, invocation, return hay receiver của một lời gọi tiếp theo.
4. **Tìm nguồn ràng buộc thật**: kiểu đích, đối số thực, type witness, diamond và cận trên của type parameter.
5. **Xác định ranh giới suy luận**: biến trung gian đã chốt kiểu; generic invocation ở vị trí receiver có thể không nhận target ngoài cùng.
6. **Kiểm tra kết quả kiểu tĩnh trước khi gọi tiếp**: List<Object> → Stream<Object> → List<Object> sẽ không tự đổi thành List<String>.
7. **Sửa tại nơi thiếu thông tin kiểu**: ghi kiểu tường minh ở biến, type witness ở generic method, tham số kiểu ở constructor, hoặc giữ biểu thức trong ngữ cảnh có target type phù hợp.

Không nên sửa bằng ép kiểu mù hoặc raw type chỉ để compiler chấp nhận: cách đó che mất nguyên nhân và có thể tạo cảnh báo unchecked hay lỗi runtime.

## 11. Tổng hợp theo ngữ cảnh

| Biểu thức | Kiểu đích sẵn có? | Điều xảy ra |
| --- | --- | --- |
| List<String> a = Collections.emptyList(); | Có, List<String> | T của emptyList được suy luận String. |
| var a = Collections.emptyList(); | Không có kiểu đích String | a là List<Object>. |
| List<String> a = identity(Collections.emptyList()); | Có, List<String> | Suy luận generic lồng nhau có thể phối hợp ràng buộc. |
| consume(Collections.emptyList()); | Có, tham số List<String> | Đối số generic được suy luận phù hợp với tham số formal. |
| List<String> a = Collections.emptyList().stream().toList(); | Có ở phép gán ngoài, nhưng thiếu ở receiver | emptyList suy luận List<Object>; phép gán lỗi. |
| List<String> a = Collections.<String>emptyList().stream().toList(); | String được chỉ rõ tại emptyList | Chuỗi có List<String> và biên dịch. |
| List<String> a = new ArrayList<>(); | Có, List<String> | Diamond suy luận ArrayList<String>. |
| var a = new ArrayList<>(); | Không có ràng buộc E cụ thể | a là ArrayList<Object>. |
| Function<String,Integer> f = String::length; | Có, functional interface | Method reference được kiểm tra theo target type. |
| var f = String::length; | Không có functional interface | Không biên dịch. |

Các dòng ví dụ có tên biến a/f giống nhau trong bảng là **các tình huống riêng**, không phải một chương trình được viết nối tiếp.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao List<String> x = identity(Collections.emptyList()); có thể hợp lệ trong khi var temp = Collections.emptyList(); rồi gán temp cho List<String> lại lỗi?

**Đáp án:** Trường hợp đầu giải ràng buộc generic trong một biểu thức đang có kiểu đích List<String>. Trường hợp sau chốt kiểu temp là List<Object> trước; kiểu đích tại phép gán sau không suy luận lại biến đó.

**Câu 2.** Tại sao List<String> x = Collections.emptyList().stream().toList(); lỗi dù vế trái đã ghi String?

**Đáp án:** emptyList() đứng ở vị trí receiver của .stream(), thiếu target List<String>; nó được suy luận List<Object> rồi loại phần tử Object lan tiếp qua Stream và toList.

**Câu 3.** Có hai cách sửa trường hợp ở câu 2 mà không dùng raw type hoặc unchecked cast?

**Đáp án:** Viết Collections.<String>emptyList().stream().toList(), hoặc tạo biến trung gian List<String> source = Collections.emptyList(); rồi gọi source.stream().toList().

**Câu 4.** Vì sao var f = String::length; không biên dịch, nhưng Function<String, Integer> f = String::length; lại hợp lệ?

**Đáp án:** Method reference cần một target functional interface để xác định chữ ký hàm; var không cung cấp chữ ký đó ở initializer.

**Câu 5.** var values = new ArrayList<>(List.of("A")); có chắc chắn là ArrayList<Object> không?

**Đáp án:** Không. Đối số List.of("A") mang thông tin phần tử String, giúp constructor suy luận ArrayList<String> ngay tại initializer.

**Ghi nhớ:** Type inference dựa trên **ràng buộc tại vị trí biểu thức được kiểm tra**. Kiểu đích có thể hỗ trợ lời gọi generic lồng nhau khi các quy tắc poly expression cho phép, nhưng không lan truyền vô điều kiện qua receiver, biến trung gian hoặc mọi kiểu biểu thức. Khi compiler suy luận không đúng ý định, cung cấp kiểu ngay tại điểm ranh giới nơi thông tin bị thiếu.
