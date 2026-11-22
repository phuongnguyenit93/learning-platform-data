# Nối chuỗi qua invokedynamic và StringConcatFactory trong Java

Từ Java 9, trình biên dịch Java sử dụng cơ chế **invokedynamic** cho các biểu thức nối chuỗi thông thường. Lời gọi động được liên kết với các bootstrap method trong **StringConcatFactory**, cho phép JVM lựa chọn cách triển khai phù hợp với kiểu dữ liệu và tối ưu hóa ở thời điểm chạy.

Nhờ vậy, mã nguồn vẫn viết tự nhiên bằng toán tử cộng chuỗi, còn compiler và JVM có thêm thông tin để tối ưu việc chuyển các toán hạng thành chuỗi. Ứng dụng thông thường nên tiếp tục dùng toán tử + cho biểu thức nối có cấu trúc rõ ràng; StringConcatFactory là cơ chế nền tảng mà compiler sử dụng và cũng là API dành cho các trường hợp xây dựng call site động chuyên biệt.

## 1. Nối chuỗi trong ngôn ngữ Java

Toán tử + thực hiện phép nối khi một toán hạng thuộc kiểu String. Ví dụ:

~~~java
String message = "User " + name + " has " + count + " items.";
~~~

Biểu thức vẫn tuân theo ngữ nghĩa Java:

- Các toán hạng được đánh giá theo thứ tự từ trái sang phải.
- Giá trị không phải String được chuyển thành biểu diễn chuỗi theo quy tắc string conversion của Java.
- Giá trị tham chiếu null được biểu diễn thành chuỗi "null".
- Nếu không có toán hạng String, + có thể vẫn là phép cộng số học.
- Kết quả của biểu thức nối là một String.

Có thể nối chuỗi với primitive, object, kết quả lời gọi method và các hằng số. Compiler phải giữ nguyên kết quả quan sát được của biểu thức khi chuyển nó thành bytecode.

Ví dụ:

~~~java
String user = "An";
int score = 95;
String message = "user=" + user + ", score=" + score;
~~~

Mã nguồn không cần gọi StringConcatFactory trực tiếp. Từ Java 9, javac có thể phát một lệnh invokedynamic cho biểu thức này và để JVM liên kết lời gọi khi cần.

## 2. invokedynamic là gì?

**invokedynamic** là một lệnh bytecode của JVM dùng để gọi một phương thức thông qua call site được liên kết bằng bootstrap method. Khác với một lệnh gọi method thông thường có symbolic reference trực tiếp tới method đích, invokedynamic mô tả kiểu lời gọi và chỉ định bootstrap method để tạo CallSite.

Với nối chuỗi, compiler phát một invokedynamic có descriptor thể hiện các toán hạng và kiểu trả về String. Ví dụ một call site có thể có kiểu:

~~~text
(String, int)String
~~~

Nó nhận một String và một int, sau đó trả về String.

Khi JVM liên kết call site lần đầu, nó gọi bootstrap method với các thông tin chính:

1. **Lookup:** đối tượng MethodHandles.Lookup đại diện cho ngữ cảnh tra cứu của class đang chứa call site.
2. **Name:** tên call site.
3. **MethodType:** kiểu tham số và kiểu trả về của lời gọi động.
4. **Bootstrap arguments:** các hằng số tĩnh được lưu cùng call site, tùy bootstrap method.

Bootstrap method trả về một CallSite có target tương thích với MethodType. JVM dùng target đó cho các lần thực hiện call site tiếp theo.

~~~text
Mã nguồn Java
   |
   | javac
   v
Bytecode có invokedynamic
   |
   | liên kết lần đầu
   v
Bootstrap method
   |
   | StringConcatFactory
   v
CallSite có MethodHandle đích
   |
   | các lần gọi tiếp theo
   v
Tạo String theo ngữ nghĩa Java
~~~

Điểm quan trọng: invokedynamic không phải một thuật toán nối chuỗi. Nó là cơ chế liên kết lời gọi động. StringConcatFactory cung cấp bootstrap method chuyên dùng để tạo call site cho phép nối chuỗi.

## 3. Vai trò của StringConcatFactory

StringConcatFactory nằm trong package java.lang.invoke và được cung cấp từ Java 9. API có hai bootstrap method chính:

~~~java
CallSite makeConcat(
    MethodHandles.Lookup lookup,
    String name,
    MethodType concatType
)
~~~

~~~java
CallSite makeConcatWithConstants(
    MethodHandles.Lookup lookup,
    String name,
    MethodType concatType,
    String recipe,
    Object... constants
)
~~~

Cả hai trả về CallSite có thể thực hiện phép nối chuỗi theo kiểu được khai báo trong concatType.

### makeConcat

makeConcat dùng khi mọi phần của kết quả đều đến từ các tham số động của call site. Kiểu trả về của concatType là String; các tham số là những giá trị cần nối.

Ví dụ kiểu:

~~~text
(String, int, boolean)String
~~~

Call site nhận ba đối số động và tạo ra một chuỗi từ các giá trị đó.

### makeConcatWithConstants

makeConcatWithConstants cho phép kết hợp:

- Các đối số động được truyền khi gọi call site.
- Các hằng số được truyền vào bootstrap method lúc liên kết.
- Văn bản cố định nằm trực tiếp trong recipe.

Cách này phù hợp với biểu thức như:

~~~text
"user=" + user + "; status=ACTIVE; count=" + count
~~~

Compiler có thể biểu diễn phần văn bản cố định và hằng số ngay trong bootstrap arguments, còn user và count là đối số động ở mỗi lần gọi.

## 4. Recipe: phân biệt đối số động và hằng số

Recipe là một chuỗi mô tả thứ tự các phần tạo nên kết quả. Ngoài các ký tự văn bản thông thường, recipe dùng hai marker đặc biệt:

| Marker | Ý nghĩa |
|---|---|
| U+0001, viết trong mã Java là \u0001 | Thay bằng đối số động tiếp theo của call site |
| U+0002, viết trong mã Java là \u0002 | Thay bằng hằng số tiếp theo trong mảng constants của bootstrap |

Ví dụ recipe:

~~~java
"user=\u0001; status=\u0002; count=\u0001"
~~~

Với MethodType:

~~~text
(String, int)String
~~~

và hằng số:

~~~java
new Object[] {"ACTIVE"}
~~~

thì các phần được ghép theo thứ tự:

1. Văn bản cố định "user=".
2. Đối số động thứ nhất, kiểu String.
3. Văn bản cố định "; status=".
4. Hằng số thứ nhất, giá trị "ACTIVE".
5. Văn bản cố định "; count=".
6. Đối số động thứ hai, kiểu int.

Nếu gọi với ("An", 3), kết quả là:

~~~text
user=An; status=ACTIVE; count=3
~~~

Số marker U+0001 phải khớp với số đối số động trong MethodType. Các marker U+0002 phải khớp với các hằng số bootstrap được cung cấp. Recipe và danh sách constants phải được xây dựng đồng bộ; nếu sai số lượng hoặc kiểu dữ liệu, việc tạo call site có thể thất bại.

Các ký tự marker là ký tự điều khiển, không phải chuỗi hai ký tự gồm dấu gạch chéo và chữ số. Khi đọc bytecode bằng javap, chúng thường được hiển thị dưới dạng escape để dễ quan sát.

## 5. MethodType xác định hợp đồng của call site

MethodType mô tả chính xác kiểu lời gọi:

~~~java
MethodType type =
    MethodType.methodType(String.class, String.class, int.class);
~~~

Kiểu này tương đương:

~~~text
(String, int)String
~~~

Đối với StringConcatFactory:

- Kiểu trả về phải là String.
- Các tham số là những giá trị động được dùng trong phép nối.
- Kiểu của từng đối số quyết định cách giá trị đó được chuyển thành chuỗi.
- Số tham số phải phù hợp với recipe nếu dùng makeConcatWithConstants.

MethodType không chỉ phục vụ kiểm tra ở compile time. Nó là một phần của hợp đồng linkage giữa invokedynamic, bootstrap method và CallSite.

Khi tự xây dựng call site, hãy tạo MethodType chính xác với kiểu thực tế của các đối số. Không dựa vào ép kiểu ngầm của Java compiler tại vị trí gọi để sửa một descriptor sai.

## 6. Quy trình liên kết call site

Một biểu thức nối chuỗi được compiler chuyển thành invokedynamic thường đi qua các bước sau:

1. **Compiler phân tích biểu thức:** xác định các toán hạng động, phần văn bản cố định và kiểu dữ liệu.
2. **Compiler tạo constant-pool entry:** entry InvokeDynamic tham chiếu tới bootstrap method và descriptor của call site.
3. **JVM gặp call site:** khi lệnh invokedynamic được thực hiện lần đầu, JVM bắt đầu quá trình linkage.
4. **Bootstrap method chạy:** StringConcatFactory nhận Lookup, tên call site, MethodType và các bootstrap arguments.
5. **CallSite được trả về:** target của call site có kiểu tương thích với descriptor.
6. **Call site được sử dụng:** các lần gọi sau đi qua target đã liên kết; JIT có thể tiếp tục tối ưu đường chạy nóng.

Linkage không có nghĩa là mỗi lần nối chuỗi đều phải gọi lại bootstrap method. Bootstrap method thiết lập call site; target của call site được dùng cho các lần gọi sau.

## 7. Vì sao Java 9 dùng invokedynamic cho phép nối chuỗi?

JEP 280 giới thiệu cách triển khai này để cải thiện khả năng tối ưu phép nối chuỗi. Compiler không cần cố định một chuỗi thao tác cụ thể trong bytecode cho mọi biểu thức. Thay vào đó, nó mô tả phép nối bằng một call site có kiểu và để StringConcatFactory/JVM lựa chọn cách triển khai.

Lợi ích thiết kế:

- **Compiler phát bytecode ổn định hơn:** chi tiết triển khai phép nối không bị đóng cứng vào từng chuỗi lệnh.
- **JVM có thêm ngữ cảnh:** bootstrap nhận kiểu của toàn bộ toán hạng và cấu trúc biểu thức.
- **Tối ưu theo runtime:** JVM có thể chọn chiến lược phù hợp với dữ liệu primitive, reference và hằng số.
- **JIT có thể tối ưu call site:** đường thực thi nóng có thể được inline hoặc tối ưu dựa trên thông tin runtime.
- **Tương thích ngữ nghĩa:** biểu thức vẫn phải cho kết quả đúng theo quy tắc nối chuỗi của Java.

Không nên diễn giải lợi ích này thành cam kết rằng mọi phép nối chuỗi trong mọi workload đều nhanh hơn một cách cố định. Kết quả thực tế còn phụ thuộc số toán hạng, kích thước chuỗi, tần suất gọi, allocation, JIT warm-up và workload tổng thể.

## 8. Nối chuỗi thông thường và khi nào dùng API khác

Với biểu thức có số phần nối hữu hạn, rõ ràng, dùng toán tử +:

~~~java
String message = "user=" + user + ", score=" + score;
~~~

Đây là cách viết dễ đọc và compiler hiện đại đã xử lý qua invokedynamic.

Với việc tích lũy nhiều phần trong vòng lặp, cân nhắc StringBuilder để thể hiện rõ một bộ đệm được cập nhật qua nhiều bước:

~~~java
StringBuilder result = new StringBuilder();

for (String part : parts) {
    if (result.length() > 0) {
        result.append(", ");
    }
    result.append(part);
}

String joined = result.toString();
~~~

Với các phần tử có dấu phân cách, API chuyên dụng có thể rõ ràng hơn:

~~~java
String joined = String.join(", ", parts);
~~~

Hoặc dùng StringJoiner khi cần prefix/suffix:

~~~java
StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("red");
joiner.add("green");
joiner.add("blue");

String colors = joiner.toString();
~~~

Việc chọn API dựa trên cấu trúc công việc và khả năng đọc hiểu, không chỉ dựa vào giả định về số allocation. Đừng tự gọi StringConcatFactory cho phép nối chuỗi thông thường; compiler đã làm việc đó.

## 9. Gọi StringConcatFactory trực tiếp

Trong thư viện xây dựng call site hoặc công cụ runtime chuyên biệt, có thể gọi bootstrap method và lấy MethodHandle từ CallSite.

Ví dụ:

~~~java
MethodType type =
    MethodType.methodType(String.class, String.class, int.class);

CallSite callSite = StringConcatFactory.makeConcatWithConstants(
    MethodHandles.lookup(),
    "concat",
    type,
    "user=\u0001; status=\u0002; count=\u0001",
    "ACTIVE"
);

MethodHandle target = callSite.dynamicInvoker();
String result = (String) target.invokeExact("An", 3);
~~~

Ở đây:

- Lookup là ngữ cảnh tra cứu của class hiện tại.
- Tên call site là "concat".
- MethodType khai báo hai đối số động String và int, kết quả String.
- Recipe chứa hai marker đối số động và một marker hằng số.
- "ACTIVE" là hằng số được chèn tại marker U+0002.
- dynamicInvoker() trả về MethodHandle đại diện cho target của CallSite.

Lời gọi invokeExact phải khớp chính xác MethodType. Trong ví dụ, đối số đầu là String, đối số thứ hai là int và kết quả được ép kiểu String.

Việc gọi makeConcatWithConstants trực tiếp trong ví dụ là lời gọi Java thông thường tới factory để minh họa hợp đồng bootstrap. Nó không tự biến dòng gọi đó thành bytecode invokedynamic. Lệnh invokedynamic thật xuất hiện khi compiler tạo call site trong bytecode hoặc khi một class file khai báo bootstrap linkage tương ứng.

## 10. Ví dụ Java chạy được: compiler và factory

Chương trình sau so sánh hai cách:

- compiler xử lý biểu thức + thông thường.
- chương trình gọi StringConcatFactory để tạo CallSite với recipe và hằng số.

~~~java
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.StringConcatFactory;

public class StringConcatIndyExample {
    static String compilerConcat(String name, int count) {
        return "user=" + name + ", count=" + count;
    }

    static String factoryConcat(String name, int count) throws Throwable {
        MethodType type =
            MethodType.methodType(String.class, String.class, int.class);

        CallSite callSite = StringConcatFactory.makeConcatWithConstants(
            MethodHandles.lookup(),
            "concat",
            type,
            "user=\u0001; status=\u0002; count=\u0001",
            "ACTIVE"
        );

        MethodHandle target = callSite.dynamicInvoker();
        return (String) target.invokeExact(name, count);
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("compiler=" + compilerConcat("An", 3));
        System.out.println("factory=" + factoryConcat("An", 3));
    }
}
~~~

Lưu trong tệp StringConcatIndyExample.java, biên dịch và chạy với Java 9 trở lên:

~~~shell
javac --release 9 -Xlint:all StringConcatIndyExample.java
java StringConcatIndyExample
~~~

Kết quả stdout chính xác:

~~~text
compiler=user=An, count=3
factory=user=An; status=ACTIVE; count=3
~~~

Phân tích:

1. compilerConcat dùng toán tử +. Khi biên dịch với Java 9, javac tạo invokedynamic call site cho biểu thức nối động.
2. factoryConcat tạo MethodType cho hai đối số động và một kết quả String.
3. makeConcatWithConstants liên kết recipe với một hằng số ACTIVE.
4. dynamicInvoker lấy MethodHandle của CallSite; invokeExact gọi target với đúng kiểu.
5. Hai cách cho kết quả khác nhau vì recipe của factory có thêm status=ACTIVE; cả hai đều tuân thủ ngữ nghĩa đã mô tả.

## 11. Kiểm tra bytecode bằng javap

Có thể xác minh compiler tạo invokedynamic bằng:

~~~shell
javap -c -v StringConcatIndyExample
~~~

Trong output, tìm các mục:

~~~text
InvokeDynamic
BootstrapMethods
java/lang/invoke/StringConcatFactory.makeConcatWithConstants
~~~

Một phần bytecode có thể có dạng:

~~~text
invokedynamic #... // InvokeDynamic #...:makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
~~~

Trong BootstrapMethods, sẽ thấy bootstrap handle trỏ tới:

~~~text
java/lang/invoke/StringConcatFactory.makeConcatWithConstants
~~~

và các bootstrap arguments có recipe chứa marker động/hằng số.

Các chỉ số constant-pool như #7 hoặc #35 có thể thay đổi theo compiler version, tên class và nội dung chương trình. Khi kiểm tra, hãy dựa vào tên bootstrap method, descriptor và recipe thay vì so sánh số chỉ mục cố định.

Có thể dùng javap -c để xem lệnh bytecode và -v để xem constant pool cùng BootstrapMethods. Đây là cách xác minh compiler output mà không cần suy đoán từ mã nguồn.

## 12. Những giới hạn và lưu ý khi tối ưu

StringConcatFactory giúp JVM có cơ hội tối ưu, nhưng không loại bỏ chi phí tạo kết quả String. Mỗi kết quả vẫn cần biểu diễn nội dung chuỗi theo ngữ nghĩa Java.

Khi đánh giá hiệu năng, chú ý:

- **Allocation:** số lượng và kích thước chuỗi kết quả, cùng các object trung gian nếu có.
- **Operand conversion:** chi phí chuyển object hoặc primitive thành chuỗi.
- **String length:** chuỗi lớn có chi phí sao chép và cấp phát lớn hơn.
- **Call frequency:** biểu thức chạy một lần khác với biểu thức nằm trong vòng lặp nóng.
- **JIT warm-up:** kết quả đo quá sớm có thể phản ánh đường interpreter hoặc compilation chưa ổn định.
- **GC pressure:** nhiều chuỗi tạm thời có thể làm tăng lượng cấp phát và hoạt động thu gom.
- **Contention:** hiệu năng của ứng dụng còn chịu ảnh hưởng bởi thread và tài nguyên dùng chung.

Không tối ưu bằng cách viết code phức tạp chỉ vì đoán compiler sẽ phát bytecode theo một dạng nhất định. Hãy đo trong workload đại diện, dùng profiler hoặc benchmark có kiểm soát, và ưu tiên cấu trúc code thể hiện đúng ý định.

Khi benchmark, tránh nối chuỗi trong chính vòng đo mà không kiểm soát dữ liệu đầu vào, dead-code elimination và warm-up. Dùng JMH cho microbenchmark cần độ tin cậy, sau đó xác nhận lại trong ứng dụng thực tế.

## 13. Lỗi thường gặp

- **Nghĩ invokedynamic là một thuật toán nối chuỗi:** nó là cơ chế linkage; StringConcatFactory cung cấp bootstrap chuyên biệt.
- **Nghĩ bootstrap method chạy lại cho mọi lần nối:** bootstrap thiết lập CallSite; các lần gọi tiếp theo dùng target đã liên kết.
- **Nhầm recipe marker U+0001 và U+0002:** marker đầu là đối số động, marker sau là hằng số bootstrap.
- **Số marker không khớp MethodType/constants:** call site có thể không được tạo thành công.
- **MethodType khai báo sai kiểu trả về:** StringConcatFactory cần kiểu trả về String.
- **Gọi invokeExact với kiểu không khớp:** lời gọi MethodHandle yêu cầu descriptor chính xác.
- **Cho rằng gọi factory trực tiếp chính là lệnh invokedynamic:** đó là lời gọi Java tới API; invokedynamic là lệnh bytecode có bootstrap linkage.
- **Tự gọi StringConcatFactory trong code nghiệp vụ:** toán tử + thường là lựa chọn rõ ràng; compiler đã dùng cơ chế phù hợp.
- **Cho rằng mọi biểu thức + đều nhanh hơn mọi cách khác:** performance phụ thuộc workload, allocation và JIT.
- **Dùng + để tích lũy vô hạn trong vòng lặp mà không đo:** cân nhắc StringBuilder, StringJoiner hoặc String.join theo cấu trúc công việc.
- **So sánh số constant-pool index giữa hai lần build:** các chỉ số có thể đổi; đọc tên bootstrap và descriptor.
- **Đo hiệu năng chỉ bằng một lần chạy:** cần warm-up, workload đại diện và công cụ benchmark phù hợp.

## 14. Tài liệu tham khảo chính thức

- StringConcatFactory — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/StringConcatFactory.html — bootstrap methods, MethodType, recipe và constants.
- CallSite — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/CallSite.html — target và dynamicInvoker.
- MethodHandle — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html — invokeExact và kiểu lời gọi.
- Java Virtual Machine Specification, invokedynamic: https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-6.html#jvms-6.5.invokedynamic — linkage và thực thi lệnh invokedynamic.
- JEP 280: Indify String Concatenation: https://openjdk.org/jeps/280 — thiết kế nối chuỗi qua invokedynamic từ Java 9.
