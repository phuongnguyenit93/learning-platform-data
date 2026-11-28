# Tránh identityHashCode và IdentityHashMap với dữ liệu có ngữ nghĩa giá trị

Trong Java, có hai cách nhìn một object: xem nó là một giá trị và xem nó là một thực thể có danh tính riêng. Với dữ liệu có ngữ nghĩa giá trị, chương trình quan tâm nội dung mà object biểu diễn. Với dữ liệu có ngữ nghĩa identity, chương trình cần phân biệt từng object cụ thể, kể cả khi hai object có nội dung giống nhau.

**System.identityHashCode()** và **IdentityHashMap** phục vụ các thao tác dựa trên identity. Chúng có chỗ dùng hợp lý, chẳng hạn theo dõi từng node riêng biệt trong một đồ thị object. Tuy nhiên, chúng không phù hợp để so sánh, định danh hoặc lưu trữ các instance của value-based class như **Integer**, **Optional** và nhiều kiểu trong **java.time**. Hợp đồng của những lớp này bảo đảm ý nghĩa giá trị, không bảo đảm identity ổn định của từng instance.

Bài học này phân biệt hash code theo giá trị với identity hash code, giải thích cách **IdentityHashMap** so sánh khóa, chỉ ra các bẫy thường gặp và hướng dẫn chọn collection phù hợp trong Java hiện đại.

## 1. Giá trị và identity là hai khái niệm khác nhau

Hai object có thể biểu diễn cùng một giá trị nhưng vẫn là hai object khác nhau:

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
~~~

- **equals()** kiểm tra hai object có bằng nhau theo hợp đồng của lớp hay không.
- **==** khi áp dụng cho hai reference kiểm tra chúng có trỏ tới cùng một object hay không.

Với value-based class, chương trình cần dựa trên giá trị. Ví dụ, hai instance **Integer** có cùng số nguyên cần được xem là có thể thay thế cho nhau trong những thao tác mà API định nghĩa:

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);

System.out.println(first.equals(second)); // true
~~~

Không có cam kết rằng hai biến phải cùng tham chiếu hoặc phải tham chiếu tới hai object riêng biệt. Factory và runtime có thể tái sử dụng instance khi hợp đồng API cho phép.

Tài liệu Java SE mô tả rõ rằng các thao tác nhạy cảm với identity trên value-based instance cần được tránh. Ví dụ được nêu gồm so sánh reference bằng **==**, identity hash code và đồng bộ hóa trên instance.

## 2. hashCode() và System.identityHashCode() khác nhau thế nào?

Cả hai đều trả về một giá trị kiểu **int**, nhưng chúng có mục đích khác nhau.

### hashCode() theo hợp đồng của lớp

**object.hashCode()** là phương thức thông thường của object. Lớp có thể ghi đè phương thức này để tính hash code từ dữ liệu tham gia vào **equals()**.

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first.equals(second)); // true
System.out.println(first.hashCode() == second.hashCode()); // true
~~~

Vì hai chuỗi bằng nhau theo **String.equals()**, chúng phải có cùng **hashCode()**. Đây là yêu cầu của hợp đồng **Object.hashCode()** và là điều kiện để các collection như **HashMap** và **HashSet** hoạt động đúng.

### System.identityHashCode() bỏ qua override hashCode()

**System.identityHashCode(object)** trả về identity hash code của object, tức giá trị như phương thức **Object.hashCode()** mặc định sẽ cung cấp, kể cả khi lớp đã ghi đè **hashCode()**.

~~~java
String value = new String("Java");

int valueHash = value.hashCode();
int identityHash = System.identityHashCode(value);
~~~

- **valueHash** được tính theo nội dung chuỗi vì **String** ghi đè **hashCode()**.
- **identityHash** không sử dụng implementation **String.hashCode()**; nó đại diện cho hash code theo identity của object.

Hai giá trị có thể tình cờ bằng nhau. Không thể dựa vào việc chúng phải khác nhau.

### Identity hash code không phải định danh duy nhất

Một identity hash code là số nguyên, không phải địa chỉ bộ nhớ và không phải mã định danh duy nhất. Hai object khác nhau có thể nhận cùng identity hash code. Vì vậy, không dùng nó làm khóa duy nhất, ID nghiệp vụ hoặc căn cứ để kết luận hai reference có cùng identity.

~~~java
Object first = new Object();
Object second = new Object();

int firstIdHash = System.identityHashCode(first);
int secondIdHash = System.identityHashCode(second);

// Không thể kết luận first == second chỉ từ hai số hash này.
~~~

Nếu hai số hash khác nhau, hai object chắc chắn không thể là cùng object trong cùng lần chạy. Nhưng nếu hai số bằng nhau, chúng vẫn có thể là hai object khác nhau do hash collision.

Đối với **null**, **System.identityHashCode(null)** trả về **0**. Điều này cũng cho thấy kết quả của phương thức không phải một ID duy nhất cho mọi object.

## 3. Vì sao không dùng identity hash code cho value-based class?

Value-based class định nghĩa equality theo giá trị. **hashCode()** thông thường của lớp được thiết kế để tương thích với **equals()**. Ngược lại, **System.identityHashCode()** cố ý bỏ qua hợp đồng giá trị để phản ánh identity của object.

Ví dụ:

~~~java
Integer first = Integer.valueOf(500);
Integer second = Integer.valueOf(500);

boolean sameValue = first.equals(second);
int firstIdentityHash = System.identityHashCode(first);
int secondIdentityHash = System.identityHashCode(second);
~~~

**sameValue** là kết quả phù hợp để kiểm tra hai giá trị số. Hai identity hash code không cho biết hai số có bằng nhau hay không. Chúng có thể bằng hoặc khác nhau tùy identity của instance; hash collision cũng có thể xảy ra.

Một số cách dùng cần tránh:

- Dùng **System.identityHashCode(value)** để tạo mã nhận diện cho một **Integer**, **Optional** hoặc **LocalDate**.
- Dùng identity hash code để nhóm các instance có cùng giá trị.
- Dùng identity hash code làm khóa trong một **HashMap<Integer, ...>** với giả định mỗi object có một số hash riêng.
- Dùng kết quả identity hash code để suy ra object có được cache hoặc tái sử dụng hay không.
- Lưu identity hash code vào dữ liệu bền vững rồi dùng lại sau khi ứng dụng khởi động lại.

Nếu nghiệp vụ cần một định danh ổn định, hãy tạo định danh rõ ràng như **UUID**, mã đơn hàng hoặc khóa nghiệp vụ. Nếu cần hash để lưu trữ theo giá trị, dùng **hashCode()** theo hợp đồng của lớp.

## 4. IdentityHashMap hoạt động khác HashMap

**HashMap** dùng equality theo hợp đồng **equals()** và **hashCode()**. Hai khóa bằng nhau theo **equals()** được xem là cùng một khóa logic.

**IdentityHashMap** thay thế phép so sánh khóa bằng reference equality. Nó phân biệt hai object theo việc chúng có cùng identity hay không, kể cả khi **equals()** trả về **true**.

Ví dụ với **HashMap**:

~~~java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> byValue = new HashMap<>();

byValue.put(new String("Java"), 1);
byValue.put(new String("Java"), 2);

System.out.println(byValue.size()); // 1
System.out.println(byValue.get("Java")); // 2
~~~

Hai chuỗi có nội dung bằng nhau nên lần put thứ hai cập nhật giá trị của cùng một khóa logic.

Cùng ví dụ với **IdentityHashMap**:

~~~java
import java.util.IdentityHashMap;
import java.util.Map;

Map<String, Integer> byIdentity = new IdentityHashMap<>();

byIdentity.put(new String("Java"), 1);
byIdentity.put(new String("Java"), 2);

System.out.println(byIdentity.size()); // 2
~~~

Hai chuỗi được tạo thành hai object khác nhau. Vì **IdentityHashMap** so sánh khóa bằng **==**, chúng được xem là hai khóa khác nhau dù **String.equals()** trả về **true**.

### IdentityHashMap so sánh cả giá trị theo identity

Theo hợp đồng API, **IdentityHashMap** sử dụng reference equality thay cho object equality khi so sánh cả khóa và giá trị. Đây là điểm khác biệt quan trọng với các implementation **Map** thông thường.

Collection này cố ý không tuân theo đầy đủ hợp đồng equality thông thường của **Map**, vốn dựa trên **equals()**. Vì vậy, không dùng **IdentityHashMap** như một phiên bản **HashMap** có hiệu năng khác hoặc như một collection mặc định cho dữ liệu ứng dụng.

## 5. Vì sao IdentityHashMap không phù hợp với value-based class?

Value-based class có thể có nhiều instance biểu diễn cùng một giá trị. Hợp đồng API không bảo đảm identity riêng cho từng instance, cũng không yêu cầu runtime luôn tái sử dụng cùng một instance.

Nếu dùng các instance đó làm khóa trong **IdentityHashMap**, kết quả lưu trữ sẽ phụ thuộc identity thực tế của object:

~~~java
import java.util.IdentityHashMap;
import java.util.Map;
import java.util.Optional;

Map<Optional<Integer>, String> labels = new IdentityHashMap<>();

Optional<Integer> first = Optional.of(10);
Optional<Integer> second = Optional.of(10);

labels.put(first, "Giá trị thứ nhất");
labels.put(second, "Giá trị thứ hai");

// Không dựa vào identity của hai Optional để dự đoán số khóa.
~~~

Hai Optional bằng nhau theo **equals()** vì chúng chứa cùng giá trị, nhưng không có cam kết rằng hai factory call phải trả về cùng reference. Vì vậy, **IdentityHashMap** có thể coi chúng là hai khóa riêng hoặc cùng một khóa nếu runtime trả về cùng instance. Cả hai hành vi đều không thích hợp làm quy tắc equality của dữ liệu.

Với dữ liệu có ngữ nghĩa giá trị, dùng **HashMap**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

Map<Optional<Integer>, String> labels = new HashMap<>();

labels.put(Optional.of(10), "Giá trị");
System.out.println(labels.get(Optional.of(10))); // "Giá trị"
~~~

**HashMap** dùng **equals()** và **hashCode()** của Optional, nên việc tìm kiếm dựa trên giá trị mà container biểu diễn.

Trong code thực tế, với khóa có thể vắng mặt, thường nên cân nhắc dùng kiểu khóa nghiệp vụ rõ ràng thay vì dùng **Optional** làm khóa. Ví dụ, có thể dùng một record chứa các field nghiệp vụ hoặc một mã định danh đã được chuẩn hóa.

## 6. Khi nào IdentityHashMap có mục đích sử dụng hợp lý?

**IdentityHashMap** không phải collection xấu. Nó giải quyết một bài toán khác: cần theo dõi từng object cụ thể, không gộp các object chỉ vì chúng bằng nhau theo **equals()**.

Một số trường hợp phù hợp:

- Sao chép đồ thị object nhưng cần giữ nguyên quan hệ tham chiếu giữa các node.
- Phát hiện object đã được duyệt trong một đồ thị có chu trình.
- Lưu metadata gắn với từng instance cụ thể.
- Xây dựng công cụ phân tích object graph, serializer hoặc framework cần phân biệt identity.

Ví dụ, khi sao chép đồ thị object, một node có thể được tham chiếu từ nhiều nơi. Bản sao cần bảo đảm các tham chiếu tới cùng node gốc cùng trỏ tới một node bản sao, thay vì tạo nhiều bản sao khác nhau.

~~~java
import java.util.IdentityHashMap;
import java.util.Map;

class Node {
    String label;
    Node next;

    Node(String label) {
        this.label = label;
    }
}

Map<Node, Node> copies = new IdentityHashMap<>();
~~~

Map **copies** có thể ánh xạ từng node gốc sang đúng một node bản sao. Nếu hai node khác nhau có cùng nội dung hoặc được một lớp định nghĩa là bằng nhau theo **equals()**, chúng vẫn cần có hai bản sao riêng khi identity của node gốc cần được bảo toàn.

Đây là bài toán identity thực sự. Các node ở đây là object có vòng đời và quan hệ tham chiếu riêng, không phải value-based instance đại diện cho dữ liệu có thể thay thế theo giá trị.

## 7. Chọn collection theo ngữ nghĩa dữ liệu

Có thể dùng bảng sau để chọn công cụ:

| Nhu cầu | Lựa chọn |
| --- | --- |
| Tìm kiếm khóa theo giá trị | **HashMap** |
| Lưu tập hợp giá trị không trùng theo **equals()** | **HashSet** |
| Duy trì thứ tự sắp xếp theo comparator | **TreeMap**, **TreeSet** |
| Phân biệt object theo reference identity | **IdentityHashMap** |
| Cần định danh nghiệp vụ ổn định | **UUID**, String ID hoặc record khóa |
| Cần hash code theo hợp đồng của lớp | **hashCode()** |
| Cần identity hash code cho chẩn đoán kỹ thuật | **System.identityHashCode()**, nhưng không dùng làm ID duy nhất |

Khi thiết kế collection, hãy tự hỏi: hai instance bằng nhau theo **equals()** có cần được xem là cùng một khóa logic không?

- Nếu có, chọn **HashMap** hoặc collection dựa trên equality theo giá trị.
- Nếu không, và từng instance thực sự có ý nghĩa riêng, có thể cân nhắc **IdentityHashMap**.
- Nếu cần một ID bền vững qua lần chạy, tạo ID rõ ràng thay vì dùng hash code.

## 8. Quy trình rà soát identity-sensitive operations

Khi review code có value-based class, hãy kiểm tra:

1. Có dùng **==** để so sánh hai instance theo giá trị hay không.
2. Có gọi **System.identityHashCode()** để định danh instance hay không.
3. Có đưa value-based instance vào **IdentityHashMap** hay collection dựa trên identity hay không.
4. Có dùng instance làm monitor cho **synchronized**, **wait()** hoặc **notify()** hay không.
5. Có lưu identity hash code thành khóa dữ liệu lâu dài hoặc truyền sang hệ thống khác hay không.
6. Có thể thay bằng **equals()**, **Objects.equals()**, **hashCode()**, **HashMap**, **HashSet** hoặc ID nghiệp vụ hay không.

Có thể bật lint category **identity** của **javac** để hỗ trợ phát hiện một số cách dùng value-based class nhạy cảm với identity:

~~~bash
javac -Xlint:identity -d out src/example/Main.java
~~~

Cảnh báo của compiler là một lớp kiểm tra bổ sung. Không phải mọi cách sử dụng gián tiếp qua helper, thư viện hoặc collection đều nhất thiết được phát hiện từ mã nguồn tại vị trí gọi. Hãy xem lại ngữ nghĩa của thao tác và hợp đồng API, không chỉ dựa vào việc build có cảnh báo hay không.

## 9. Kết luận

**System.identityHashCode()** và **IdentityHashMap** phục vụ các thao tác dựa trên identity của object. Identity hash code không phải ID duy nhất; **IdentityHashMap** cố ý so sánh khóa và giá trị theo reference thay vì equality theo nội dung.

Với value-based class, hãy dùng **equals()** và **hashCode()** theo hợp đồng giá trị, lưu trữ bằng **HashMap** hoặc **HashSet**, và tạo ID nghiệp vụ riêng khi cần định danh ổn định. Chỉ chọn **IdentityHashMap** khi thuật toán thực sự cần phân biệt từng object cụ thể, chẳng hạn khi duyệt hoặc sao chép đồ thị object.

## Tài liệu tham khảo

- [Value-based Classes — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/doc-files/ValueBased.html)
- [System.identityHashCode() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object))
- [IdentityHashMap — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/IdentityHashMap.html)
- [Object.hashCode() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Object.html#hashCode())
- [Object.equals() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object))
- [HashMap — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/HashMap.html)
- [JEP 390: Warnings for Value-Based Classes](https://openjdk.org/jeps/390)
- [The javac Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)

