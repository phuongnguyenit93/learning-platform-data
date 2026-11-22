# Khi nào `String.intern()` có ích và giới hạn khi dùng trên dữ liệu không kiểm soát

`String.intern()` cho phép nhiều chuỗi **có nội dung bằng nhau** dùng chung một đối tượng đại diện (*canonical string*) trong **string pool** của JVM. Ý tưởng này hữu ích khi dữ liệu lặp lại rất nhiều và số giá trị khác nhau được khống chế. Ngược lại, với các giá trị do người dùng hoặc hệ thống bên ngoài tự do tạo ra, số chuỗi khác nhau có thể tăng vô hạn theo thời gian; intern tràn lan có thể làm tốn CPU, gây áp lực bộ nhớ, GC và ảnh hưởng hiệu năng toàn JVM.

Bài này giải thích cơ chế, điều kiện nên dùng, giới hạn với dữ liệu không tin cậy, lựa chọn thay thế và cách đo đạc. Các ví dụ sử dụng Java 17+.

## 1. Hiểu đúng cơ chế String pool và `intern()`

Trong Java, `String` bất biến (*immutable*). Hai đối tượng có thể cùng nội dung nhưng khác tham chiếu:

- `a.equals(b)` hỏi **nội dung** có giống nhau hay không.
- `a == b` hỏi có cùng **tham chiếu đối tượng** hay không.
- `a.intern()` yêu cầu JVM trả về đối tượng đại diện cho nội dung của `a` trong pool. Nếu pool có đại diện bằng nội dung thì trả đối tượng đó, nếu chưa có thì đưa một đại diện vào pool rồi trả lại.

Với hai chuỗi bằng nhau về nội dung, hợp đồng API `String.intern()` bảo đảm hai kết quả `intern()` là cùng tham chiếu. Phép gọi **không thay đổi biến nhận** nếu bạn không gán lại:

~~~java
String a = new String("READY");
String b = new String("READY");

System.out.println(a == b);               // false
System.out.println(a.equals(b));          // true
System.out.println(a.intern() == b.intern()); // true

String canonical = a.intern();
System.out.println(canonical == "READY");  // true
System.out.println(a == "READY");          // false
~~~

Literal như `"READY"` và biểu thức hằng `"REA" + "DY"` được canonical hóa qua cơ chế liên quan đến string pool. Một biểu thức ghép thực thi lúc chạy không được bảo đảm có cùng tham chiếu:

~~~java
String a = "READY";
String b = "REA" + "DY"; // compile-time constant
String suffix = "DY";
String c = "REA" + suffix; // biểu thức không phải constant expression

System.out.println(a == b);          // true
System.out.println(a.equals(c));     // true
System.out.println(a == c);          // false
System.out.println(a == c.intern()); // true
~~~

**Nguyên tắc quan trọng:** Dù có intern ở một phần hệ thống, các API khác vẫn có thể tạo `String` không intern. Vì vậy so sánh trạng thái nghiệp vụ từ nhiều nguồn **bằng `equals()`**, hoặc `Objects.equals(a,b)` nếu có thể null. Chỉ so `==` đối với String khi có hợp đồng nội bộ rõ ràng bảo đảm **mọi** đường tạo/nhận giá trị đều canonical; tránh dùng nó như một giả định ngầm.

## 2. Pool có giống cache ứng dụng không?

String pool là tài nguyên ở phạm vi JVM, không phải cache cục bộ mà code tùy ý xóa một entry bằng `remove()`. Triển khai cụ thể khác nhau theo JVM, JDK và collector. Trên HotSpot hiện đại (bao gồm Java 17), việc quản lý đối tượng chuỗi gắn với Java heap; thông tin lịch sử rằng toàn bộ interned strings nằm vĩnh viễn trong *PermGen* của các phiên bản rất cũ không còn là mô hình phù hợp.

Hai cực đoan đều không đúng:

1. **“Hễ intern là giữ chuỗi vĩnh viễn.”** Không được khẳng định chung cho mọi JVM. Khả năng thu hồi một đại diện phụ thuộc việc còn tham chiếu mạnh từ ứng dụng, literal/constant liên quan, JVM và chính sách collector. Một số chuỗi có thể được thu hồi khi không còn reachable.
2. **“GC chắc chắn thu hồi kịp nên intern mọi input không sao.”** Cũng không đúng. Chương trình không quyết định khi nào GC diễn ra, không có API evict riêng cho pool, và vẫn phải trả chi phí tạo/tra cứu/quản lý các giá trị mới. Những giá trị còn được ứng dụng giữ sẽ không được thu hồi chỉ vì chúng đã intern.

Không được thiết kế theo giả định chuỗi intern luôn *leak* vĩnh viễn, cũng không dựa vào giả định chúng biến mất tức thì. Các khác biệt giữa JVM/GC cần kiểm tra trên môi trường chạy thực tế.

## 3. Điều kiện `intern()` có thể đem lại lợi ích

### 3.1. Tập giá trị nhỏ và lặp rất nhiều

Ví dụ một hệ thống giữ hàng triệu đối tượng sự kiện; mỗi sự kiện chứa một trạng thái tạo từ dữ liệu đã parse, nhưng trạng thái chỉ có `READY`, `RUNNING`, `DONE`. Nếu mỗi lần parse sinh một đối tượng `String` mới và những đối tượng sự kiện sống lâu, nhiều String giữ nội dung giống nhau có thể chiếm heap.

Trong mô hình trực giác với \(N\) lần xuất hiện và \(U\) giá trị khác nhau, khi \(U\) nhỏ hơn nhiều so với \(N\), thay nhiều bản sao chuỗi sống bằng \(U\) đại diện dùng chung có thể giảm bộ nhớ. Tuy nhiên đây **không phải công thức chính xác về byte**: kích thước object, compact string, sharing của mảng byte, tối ưu JVM, overhead của StringTable và vòng đời đối tượng đều ảnh hưởng thực tế.

Những tiêu chí để cân nhắc:

- **Cardinality có giới hạn đáng tin**: tập giá trị khác nhau được kiểm soát bằng danh sách hoặc quy tắc có ngưỡng rõ.
- **Tần suất trùng lặp cao**: nhiều đối tượng cùng giữ các nội dung giống nhau.
- **Chuỗi được giữ đủ lâu**: lợi ích giảm heap sống bù cho công tạo chuỗi và tra cứu pool.
- **Đã kiểm soát đầu vào**: giá trị lạ, quá dài hoặc vượt chính sách bị từ chối **trước** khi intern.
- **Đo được cải thiện**: heap sau GC, chi phí cấp phát, CPU, GC, throughput và độ trễ dưới tải đại diện.

Nếu chỉ vài hằng chuỗi `static final` hoặc literal được tái dùng, chúng có thể đã chia sẻ tham chiếu; thêm `intern()` không mang lại lợi ích.

### 3.2. Các tên nhãn lặp trong cấu trúc dữ liệu

Trong một parser, một cây cú pháp lớn hoặc hệ thống metadata, nhiều node có thể mang cùng tên nhãn như `"identifier"`, `"literal"`, `"property"`. Nếu chúng được tạo từ các lát dữ liệu đầu vào riêng và được giữ lâu, canonicalization có thể giảm số đối tượng/nội dung trùng được lưu giữ.

Tuy nhiên, phải xác định **đang tối ưu gì**: một chương trình tạo String tạm rồi loại bỏ ngay không nhất thiết hưởng lợi. Chỉ vì `HashMap<String, V>` có nhiều lookup cũng không có nghĩa cần intern key: `String.hashCode()` và `String.equals()` vốn giúp Map tìm đúng key có cùng nội dung dù khác tham chiếu.

### 3.3. Tối ưu đồng nhất trong một module khép kín

Một số thuật toán nội bộ có thể dựa vào canonicalization để dùng `==` sau khi biết chắc mọi giá trị đi qua một cổng chuẩn hóa. Cách này dễ lỗi nếu có đường dữ liệu mới bỏ qua bước chuẩn hóa. Nên cân nhắc `enum`, ID số nguyên hoặc symbol table của module nếu danh mục giá trị có giới hạn và quy ước nội bộ khó duy trì.

**Đừng coi `intern()` là thủ thuật mặc định để String so sánh “nhanh hơn”.** Tra cứu StringTable cũng có chi phí. Lợi ích so sánh, nếu có, phải được đo toàn đường xử lý chứ không chỉ thời gian của phép `==`.

## 4. Dữ liệu không kiểm soát nguy hiểm ở đâu?

“Không kiểm soát” có nghĩa là hệ thống không bảo đảm được số giá trị khác nhau, độ dài hoặc tốc độ xuất hiện. Những nguồn điển hình:

- UUID, request ID, trace ID, session ID, nonce, token ngẫu nhiên.
- Tên người dùng hoặc chuỗi tìm kiếm tự do.
- URL đầy đủ với query string tùy ý.
- HTTP header, giá trị JSON, nội dung log, filename hoặc payload từ client.
- Chuỗi sinh bởi dịch vụ bên ngoài với schema không ràng buộc cardinality.

Anti-pattern:

~~~java
// Minh họa anti-pattern, không phải một chương trình chạy độc lập:
String userInput = request.getParameter("key");
String key = userInput.intern(); // đưa dữ liệu chưa giới hạn vào pool
~~~

Nếu một client gửi 100.000 giá trị gần như đều khác nhau, `intern()` hầu như không tìm thấy chuỗi trùng để chia sẻ. Chương trình vẫn phải chịu chi phí xây dựng/tra cứu bảng, xử lý đối tượng và có thể áp lực GC; trên hệ thống chịu tải cao, đây có thể là một điểm làm giảm throughput hoặc tăng tail latency. Nếu lượng giá trị mới liên tục hoặc có độ dài lớn, tài nguyên có thể bị tiêu hao theo cách kẻ gửi dữ liệu điều khiển được, tạo nguy cơ từ chối dịch vụ.

**Không đồng nghĩa “mọi chuỗi intern sẽ bị giữ vĩnh viễn”.** Dù JVM có thể thu gom một số đại diện không còn reachable, điều đó không làm `intern()` phù hợp với input vô hạn. Tần suất, độ dài, việc ứng dụng giữ tham chiếu và khả năng thu gom mới quyết định tác động.

Chỉ `strip()`, `toLowerCase()` hoặc chuẩn hóa Unicode **không** làm số giá trị trở nên hữu hạn; còn phải có whitelist/giới hạn thật. Kiểm tra số entry mà bỏ qua độ dài cũng không đủ: một entry có thể chứa dữ liệu rất lớn.

### Bảng quyết định nhanh

| Dữ liệu | Có nên intern? | Hướng xử lý phù hợp |
|---|---|---|
| `READY`, `RUNNING`, `DONE` cố định | Có thể nhưng thường không cần | Ưu tiên `enum` hoặc hằng chung |
| Tên token thuộc grammar giới hạn | Cân nhắc sau khi đo | Canonical hóa sau xác thực hoặc dùng symbol table |
| Nhãn từ bộ cấu hình có giới hạn | Có thể | Giới hạn số giá trị và chiều dài, đo thực tế |
| Request ID/UUID mỗi request | Không | Giữ String bình thường, chỉ giữ khi cần |
| URL và query string tùy ý | Không | Kiểm tra định dạng, giới hạn chiều dài, tránh giữ không cần thiết |
| Tên tài khoản/tìm kiếm tự do | Không | Validation và cấu trúc dữ liệu thông thường |
| Dòng log/JSON payload bất kỳ | Không | Parse phần cần thiết, không intern cả payload |
| String key của `HashMap` | Không bắt buộc | `equals/hashCode` đủ để tra cứu đúng |

## 5. Quy trình dùng intern có kiểm soát

Một chính sách hợp lý là **validate trước, intern sau, đo cuối**.

1. Đầu tiên xác định dữ liệu nào đang lặp nhiều, có được giữ lâu hay không. Dùng profiler/heap dump/JFR thay vì đoán từ số lần tạo chuỗi.
2. Xác định **tập giá trị chấp nhận**. Với các trạng thái, dùng whitelist hoặc enum. Với nhãn do cấu hình tạo, xác định ngưỡng số giá trị và kích thước.
3. Giới hạn độ dài và tần suất đầu vào ở ranh giới nhận dữ liệu. Đây là biện pháp chung để không cho client cung cấp input cực lớn.
4. Chuẩn hóa nếu quy tắc nghiệp vụ yêu cầu; sau đó kiểm tra chính xác giá trị được phép. Các chuẩn hóa có thể thay đổi ngữ nghĩa ngôn ngữ; chọn `Locale.ROOT` khi làm việc với mã máy không phụ thuộc locale, không áp dụng bừa cho tên người dùng.
5. Chỉ gọi `intern()` cho giá trị đã hợp lệ, và **dùng tham chiếu trả về**.
6. Đo và so sánh với lựa chọn đơn giản hơn. Giữ `equals()` cho mọi API không bảo đảm identity.

## 6. Ví dụ Java 17 hoàn chỉnh: whitelist trước khi intern

Đoạn dưới đây minh họa khác biệt `==`/`equals()`, việc gọi `intern()` sau validation và lựa chọn `enum` khi tập trạng thái cố định. Lưu nguyên file UTF-8 với tên `InternSafetyDemo.java`.

~~~java
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class InternSafetyDemo {
    private static final Set<String> ALLOWED = Set.of("NEW", "READY", "DONE");

    enum Status {
        NEW, READY, DONE
    }

    static String internValidatedStatus(String raw) {
        Objects.requireNonNull(raw, "raw");
        String normalized = raw.strip().toUpperCase(Locale.ROOT);
        if (!ALLOWED.contains(normalized)) {
            throw new IllegalArgumentException("Unknown status");
        }
        return normalized.intern();
    }

    static Status parseStatus(String raw) {
        Objects.requireNonNull(raw, "raw");
        return Status.valueOf(raw.strip().toUpperCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        String first = new String(new char[] {'R', 'E', 'A', 'D', 'Y'});
        String second = new String(new char[] {'R', 'E', 'A', 'D', 'Y'});

        System.out.println("rawIdentity=" + (first == second));
        System.out.println("rawContent=" + first.equals(second));

        String a = internValidatedStatus(first);
        String b = internValidatedStatus(" ready ");
        System.out.println("canonicalIdentity=" + (a == b));
        System.out.println("sameAsLiteral=" + (a == "READY"));

        Status e1 = parseStatus(first);
        Status e2 = parseStatus(" ready ");
        System.out.println("enumIdentity=" + (e1 == e2));

        boolean rejected = false;
        try {
            internValidatedStatus("CLIENT_CUSTOM_00001");
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("unknownRejected=" + rejected);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 InternSafetyDemo.java
java InternSafetyDemo
~~~

Stdout:

~~~text
rawIdentity=false
rawContent=true
canonicalIdentity=true
sameAsLiteral=true
enumIdentity=true
unknownRejected=true
~~~

`first` và `second` là hai String tạo tường minh bằng `new`, do đó tham chiếu khác nhưng `equals()` bằng nhau. `internValidatedStatus()` chuẩn hóa rồi chỉ cho qua ba mã có sẵn; kết quả canonical trùng tham chiếu literal `"READY"`. Trường hợp lạ bị từ chối trước intern. `enum` có các instance duy nhất cố định nên so `==` đúng ngữ nghĩa enum.

**Vì sao code còn dùng intern dù enum tốt hơn?** Để minh họa ranh giới bảo vệ. Trong ví dụ đúng ba trạng thái cố định, `enum` hoặc trả trực tiếp ba literal còn đơn giản hơn, vì literal đã ở pool. Intern đáng cân nhắc hơn khi từ vựng được dựng lúc chạy nhưng có **giới hạn thực sự**, xuất hiện lặp lại và được giữ lâu; vẫn phải đo lợi ích.

## 7. Những lựa chọn thay thế đáng cân nhắc

### 7.1. Enum, hằng và ID

Khi tập giá trị cố định tại lúc phát triển, `enum` có type safety, tập phần tử hữu hạn và identity ổn định. `switch` trên enum rõ ý hơn so String và dễ quản lý đường nhập. Nếu phần tử xuất hiện trong cấu trúc dữ liệu rất lớn, ID số nguyên hoặc một mã đại diện riêng có thể thích hợp. Khi `Enum.valueOf()` nhận input ngoài tập, cần xử lý `IllegalArgumentException`; với null, cần kiểm tra riêng.

### 7.2. Cache/symbol table cục bộ có giới hạn

Khi cần canonical hóa các chuỗi runtime, một cache cục bộ có **maximum size**, giới hạn độ dài, TTL/LRU hoặc khả năng loại bỏ rõ ràng có thể dễ kiểm soát hơn pool JVM. Cần tính đến đồng bộ nếu cache dùng chung nhiều thread, chính sách loại bỏ khi đầy và overhead cache; không phải mọi chuỗi ngắn ngủi đều cần cache.

Không tự cho rằng `WeakHashMap<String, String>` với **cùng đối tượng** làm key và value sẽ tự dọn entry: value mạnh giữ sống key, chống lại ý định weak key. Các cấu trúc weak/soft references đòi hỏi hiểu reference graph và kiểm thử bộ nhớ; một thư viện cache có giới hạn thường dễ dùng đúng hơn.

### 7.3. String deduplication của GC khác intern

Một số JVM/collector hỗ trợ **String Deduplication**, chẳng hạn G1 trên HotSpot khi bật tùy chọn phù hợp như `-XX:+UseStringDeduplication`. Deduplication có thể cho nhiều đối tượng `String` **chia sẻ mảng byte chứa nội dung**, nhưng **không bắt buộc hợp nhất bản thân các đối tượng String**. Vì vậy:

- String deduplication có thể giảm vùng lưu nội dung, nhưng `a == b` vẫn có thể false.
- `intern()` trả về cùng một đại diện String khi các nội dung bằng nhau.
- Cả hai đều có chi phí/điều kiện riêng; tính khả dụng và hiệu quả phụ thuộc JVM và collector, phải kiểm chứng với cấu hình thật.

Không nên bật cấu hình hoặc thay code chỉ dựa vào phỏng đoán rằng một kỹ thuật luôn nhanh hơn.

## 8. Đo hiệu quả thế nào?

Cần ít nhất hai bộ tải:

| Tải đo | Dữ liệu | Các chỉ số quan trọng |
|---|---|---|
| Lặp cao, vocabulary nhỏ | Hàng triệu lần xuất hiện với ít mã khác nhau | Heap sống sau GC, số lượng String/mảng byte, allocation, throughput |
| Cardinality cao, dữ liệu đến liên tục | Phần lớn giá trị mới, có thể rất dài | CPU tra cứu, allocation, GC pause, độ trễ đuôi, mức dùng heap |

Dùng profiler allocation/heap, Java Flight Recorder và GC logs theo hoàn cảnh. Nếu có công cụ JDK, `jcmd <pid> GC.class_histogram` giúp quan sát số đối tượng theo class; **riêng histogram không chứng minh số chuỗi trùng nội dung**. Đo microbenchmark bằng JMH thay vì một vòng lặp `System.nanoTime()` ngắn vì JVM có JIT, warmup và GC khiến kết quả lệch.

Tiêu chí ra quyết định gồm: có giảm **heap sống thực** không, có tăng CPU/latency/GC không, có làm hệ thống chịu tải nhập dữ liệu mới kém hơn không, và liệu enum hoặc cache giới hạn có tốt hơn không. Nếu khác biệt không đáng kể, ưu tiên cách đơn giản và dễ kiểm soát.

## 9. Sai lầm phổ biến và cách nhớ

| Nhận định sai | Cách hiểu đúng |
|---|---|
| Mọi String cùng nội dung đều `==` | Chỉ `equals()` kiểm tra nội dung; `==` kiểm tra tham chiếu |
| `intern()` sửa String gốc | Trả về tham chiếu canonical; cần gán lại nếu muốn dùng |
| `intern()` luôn tiết kiệm RAM | Còn chi phí tra cứu, pool và tạo chuỗi tạm |
| Interned String luôn bất tử | Vòng đời phụ thuộc JVM, GC và tham chiếu; không khẳng định chung |
| GC sẽ dọn nhanh nên cứ intern mọi input | Không kiểm soát được GC hay vòng đời pool; input mới liên tục vẫn gây chi phí |
| Intern trước để biến input thành hợp lệ | Phải validation và giới hạn **trước** intern |
| `HashMap` cần intern key | `String.equals()` và `hashCode()` đã xử lý khóa theo nội dung |
| String deduplication làm hai String cùng `==` | Có thể chia sẻ dữ liệu byte mà vẫn là hai object |

## 10. Checklist thực hành

- [ ] Tập giá trị có giới hạn đáng tin về **cardinality**, **độ dài** và **tần suất**.
- [ ] Đã xác minh có nhiều String trùng nội dung sống đủ lâu.
- [ ] Mọi nguồn không tin cậy đều qua ràng buộc, validation và chuẩn hóa phù hợp trước intern.
- [ ] Đã thử `enum`, constants, ID hoặc cache cục bộ có giới hạn.
- [ ] Không dựa vào `==` ở ranh giới mà String có thể chưa canonical.
- [ ] Đã đo cả dữ liệu nhiều lặp lẫn trường hợp đầu vào có rất nhiều giá trị mới.
- [ ] Lợi ích bộ nhớ/hiệu năng thật sự bù được chi phí CPU, GC và độ phức tạp.

`intern()` phù hợp **khi đầu vào có từ vựng giới hạn, trùng lặp nhiều, được giữ lâu và việc chia sẻ đã được đo có ích**. Không intern đại trà chuỗi do người dùng hoặc bên thứ ba tự do cung cấp; với dữ liệu như vậy, ưu tiên validation, `equals()` và cách lưu trữ có giới hạn do ứng dụng kiểm soát.