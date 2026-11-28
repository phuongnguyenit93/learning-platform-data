# Tương tác với căn chỉnh đối tượng, tham chiếu nén, khóa và bộ thu gom rác

> **Chương:** Header đối tượng gọn  
> **Học phần:** `JAVA_VERSION_JAVA25` — các khả năng Java 25 còn áp dụng trong phát triển hiện đại như chương trình nguồn gọn, module import, flexible constructor bodies, ScopedValue, KDF API, AOT cache và JFR.  
> **Trọng tâm bài:** Hiểu Compact Object Headers làm thay đổi bố cục object trong HotSpot như thế nào; phân biệt căn chỉnh object, compressed ordinary object pointers và compressed class pointers; giải thích tác động tới khóa, GC, footprint và hiệu năng; biết bật, xác minh và benchmark trên JDK 25.

## 1. Vì sao cần giảm kích thước object header?

Mỗi object Java được cấp phát trên heap đều cần một vùng metadata do JVM quản lý. Metadata này giúp HotSpot biết object thuộc class nào, trạng thái khóa ra sao, identity hash code đã được tạo hay chưa và một số thông tin phục vụ garbage collection.

Với HotSpot 64-bit, object header truyền thống thường chiếm:

- **96 bit (12 byte)** khi class pointer được nén.
- **128 bit (16 byte)** khi class pointer không được nén.

Đối với object nhỏ chỉ chứa một vài field, phần header có thể chiếm tỷ lệ lớn trong tổng kích thước. Một ứng dụng có hàng triệu object như node trong graph, entry của `HashMap`, DTO, object trong cache hoặc cấu trúc cây có thể dành một lượng heap đáng kể cho metadata lặp lại này.

**Compact Object Headers** giảm header của object trong Java heap xuống **64 bit (8 byte)** trên HotSpot 64-bit. JDK 25 đưa tính năng từ giai đoạn experimental của JDK 24 thành product feature qua **JEP 519**. Khi bật, tài liệu Oracle ước tính giảm trung bình khoảng **4 byte trên mỗi object**; mức giảm thực tế còn phụ thuộc field layout và object alignment.

Ví dụ phép tính quy mô:

| Số object đang sống | Tiết kiệm trung bình minh họa |
|---:|---:|
| 1 triệu | khoảng 4 MB |
| 10 triệu | khoảng 40 MB |
| 50 triệu | khoảng 200 MB |
| 100 triệu | khoảng 400 MB |

Đây là phép nhân từ mức trung bình 4 byte/object, không phải dự báo chính xác cho mọi heap. Một object có nhiều field hoặc một array lớn có thể có tỷ trọng header nhỏ hơn nhiều so với object rỗng hoặc object rất nhỏ.

### 1.1. Lợi ích kỳ vọng

Header nhỏ hơn có thể tạo ra một số lợi ích liên tiếp:

1. Cùng một số lượng object cần ít heap hơn.
2. Với cùng heap limit, ứng dụng có thể giữ được nhiều object hơn trước khi chạm ngưỡng áp lực bộ nhớ.
3. Object được đặt gần nhau hơn, có thể cải thiện data locality và tận dụng cache của CPU tốt hơn.
4. Allocation và GC có thể xử lý ít byte hơn cho cùng một tập object.
5. Một số workload object-dense có thể tăng throughput hoặc giảm latency.

Không có bảo đảm mọi ứng dụng sẽ nhanh hơn. Nếu ứng dụng chủ yếu giữ byte array lớn, direct buffer, dữ liệu off-heap hoặc một số ít object lớn, header chỉ chiếm phần nhỏ tổng bộ nhớ. Khi đó lợi ích có thể không đáng kể.

## 2. Compact Object Headers trong Java 25: trạng thái và cách bật

Tính năng có lịch sử theo phiên bản như sau:

| Phiên bản | Trạng thái |
|---|---|
| JDK 24 | JEP 450, experimental; cần mở khóa experimental VM options |
| **JDK 25** | JEP 519, product feature; có thể bật trực tiếp bằng `-XX:+UseCompactObjectHeaders` |
| JDK 25 mặc định | **Tắt**; ứng dụng chỉ dùng compact headers khi chủ động bật |
| JDK mới hơn | Kiểm tra release notes của đúng phiên bản và vendor trước khi giả định default đã thay đổi |

Lệnh bật trên Java 25:

```bash
java -XX:+UseCompactObjectHeaders -jar app.jar
```

Không cần thêm `-XX:+UnlockExperimentalVMOptions` cho JDK 25. Cờ `UseCompactObjectHeaders` đã là product option. Không sao chép nguyên lệnh bật experimental của JDK 24 vào hướng dẫn Java 25.

Có thể xem giá trị flag được JVM công bố:

```bash
java -XX:+PrintFlagsFinal -version
```

Trên Linux/macOS có thể lọc:

```bash
java -XX:+PrintFlagsFinal -version | grep UseCompactObjectHeaders
```

Trên PowerShell:

```powershell
java -XX:+PrintFlagsFinal -version | Select-String UseCompactObjectHeaders
```

Kết quả mong đợi khi bật là giá trị `true` và flag được ghi nhận từ command line. Nếu muốn xem các flag của process đang chạy, có thể dùng:

```bash
jcmd <pid> VM.flags -all
```

Không chỉ nhìn thấy flag trên script triển khai rồi kết luận JVM thực sự đã dùng nó. Cần xác nhận đúng JDK executable, đúng process/container và cấu hình có hiệu lực.

### 2.1. Bật/tắt để làm đối chứng

Trong JDK 25, mặc định là không bật. Hai biến thể benchmark có thể viết như sau:

```bash
# Baseline: header truyền thống theo mặc định JDK 25
java -Xms4g -Xmx4g -jar app.jar

# Thử nghiệm: compact object headers
java -Xms4g -Xmx4g \
     -XX:+UseCompactObjectHeaders \
     -jar app.jar
```

Khi cần ép baseline rõ ràng trong script:

```bash
java -XX:-UseCompactObjectHeaders -jar app.jar
```

Dùng cùng JDK 25 build, cùng GC, heap size, CPU limit, container limit, dữ liệu và workload khi so sánh. Không so một lần chạy Java 24 experimental với một lần chạy Java 25 product rồi quy mọi khác biệt cho header.

### 2.2. Cập nhật trạng thái trên JDK 27

Bài học thuộc module Java 25, nhưng khi áp dụng vào môi trường hiện tại cần lưu ý thay đổi mặc định ở JDK mới hơn:

| Phiên bản | Mặc định compact header | Cách điều khiển |
|---|---|---|
| JDK 25 | Tắt | Bật bằng `-XX:+UseCompactObjectHeaders` |
| JDK 26 | Tắt | Bật bằng `-XX:+UseCompactObjectHeaders` |
| **JDK 27** | **Bật mặc định** | Có thể tắt bằng `-XX:-UseCompactObjectHeaders` khi cần đối chứng hoặc điều tra regression |

JDK 27 đưa compact headers thành layout mặc định qua **JEP 534 — Compact Object Headers by Default**. Vì vậy, trên JDK 27, lệnh chạy bình thường đã dùng compact headers; muốn so với layout cũ cần chỉ định rõ `-XX:-UseCompactObjectHeaders`. Oracle cho biết cờ tắt này dự kiến được deprecate và loại bỏ trong một bản phát hành tương lai, nên chỉ dùng nó khi cần đối chứng có chủ đích, không xây chính sách triển khai dài hạn phụ thuộc vào việc giữ layout cũ.

Một thay đổi liên quan: `UseCompressedClassPointers` đã deprecated trong JDK 25 và trở thành obsolete/removed trong JDK 27. Không truyền cờ này để cố bật/tắt class pointer compression; HotSpot JDK 27 luôn nén class pointers trong object. Compact header dùng encoding này như một phần của layout.

Ví dụ benchmark đối chứng trên JDK 27:

```bash
# JDK 27: compact headers bật theo mặc định
java -Xms4g -Xmx4g -jar app.jar

# JDK 27: layout cũ để làm đối chứng ngắn hạn
java -Xms4g -Xmx4g \
     -XX:-UseCompactObjectHeaders \
     -jar app.jar
```

## 3. Bố cục object: header, fields, array length và padding

Một object HotSpot có thể được hình dung ở mức khái niệm như sau:

```text
Object thường (64-bit HotSpot, class pointer nén)
+-------------------------------+
| Mark word                     | 8 byte
+-------------------------------+
| Compressed class pointer      | 4 byte
+-------------------------------+
| Instance fields               | kích thước thay đổi
+-------------------------------+
| Padding theo alignment        | nếu cần
+-------------------------------+

Compact Object Header
+-------------------------------+
| Packed 64-bit object header    | 8 byte
| (class + mark/GC/lock metadata)|
+-------------------------------+
| Instance fields               | kích thước thay đổi
+-------------------------------+
| Padding theo alignment        | nếu cần
+-------------------------------+
```

Ở header truyền thống, mark word và class pointer nằm ở hai phần riêng. Compact header đóng gói thông tin class vào một vùng 64-bit chung với các metadata khác. Với compact layout, compressed class pointer được biểu diễn bằng encoding nhỏ hơn để phù hợp trong header.

**Header không phải toàn bộ object.** Kích thước object còn phụ thuộc:

- Các instance field và kiểu dữ liệu.
- Padding để field đáp ứng natural alignment.
- Padding cuối object để địa chỉ object tiếp theo đáp ứng object alignment.
- Array length và bố cục element nếu là array.
- Quy tắc layout cụ thể của HotSpot trên nền tảng đang chạy.

Vì thế, giảm header từ 12/16 byte xuống 8 byte không đồng nghĩa mọi object đều nhỏ hơn đúng 4/8 byte. Có object tiết kiệm nhiều hơn do giảm padding; có object sau khi làm tròn alignment chỉ tiết kiệm ít hơn; có object lớn mà khác biệt rất nhỏ theo tỷ lệ.

### 3.1. Ví dụ về padding

Giả sử object có một `int`:

```java
final class Counter {
    int value;
}
```

Giả sử runtime dùng object alignment 8 byte:

- Header truyền thống với compressed class pointer có thể chiếm 12 byte.
- Field `int` chiếm 4 byte.
- Tổng 16 byte, đã là bội số của 8.
- Compact header chiếm 8 byte, field `int` thêm 4 byte.
- Tổng payload là 12 byte, sau đó làm tròn lên 16 byte.

Trong ví dụ đơn giản này, kích thước instance cuối cùng có thể vẫn là 16 byte vì padding cuối object hấp thụ phần header được rút gọn. Một class không có field hoặc có tổ hợp field khác có thể cho mức tiết kiệm khác.

Không dùng ví dụ này để suy ra kích thước mọi class. Muốn biết layout thực tế, đo bằng công cụ object-layout trên đúng JDK và flags đang triển khai.

## 4. Căn chỉnh object (`ObjectAlignmentInBytes`) ảnh hưởng ra sao?

**Object alignment** quy định địa chỉ bắt đầu của object trên heap phải thỏa một ranh giới byte nhất định. Trong HotSpot, giá trị mặc định thường là **8 byte**. JDK 25 cho phép `ObjectAlignmentInBytes` là lũy thừa của 2 trong khoảng 8 đến 256 byte.

Một object có thể cần padding để kích thước cấp phát là bội số của alignment. Alignment lớn hơn có thể tạo thêm khoảng trống giữa các object.

Ví dụ khái niệm với alignment 8 byte:

```text
Object A: bắt đầu tại offset 0, chiếm 24 byte
Object B: bắt đầu tại offset 24
Object C: bắt đầu tại offset 40
```

Với alignment 16 byte, object B hoặc C có thể phải bắt đầu tại ranh giới 16 byte kế tiếp, tạo thêm padding tùy kích thước object. Đây là ví dụ minh họa, không phải địa chỉ hay layout cố định của JVM.

### 4.1. Tại sao alignment liên quan tới compressed references?

Compressed oops biểu diễn tham chiếu object bằng offset 32-bit được scale theo object alignment, thay vì lưu một địa chỉ native 64-bit đầy đủ. Với alignment 8 byte, 32-bit offset có thể biểu diễn vùng heap xấp xỉ 32 GB theo mô hình thông thường.

JDK mô tả giới hạn heap addressable theo alignment:

\[
\text{Compressed pointer range} \approx 4\text{ GB} \times \text{ObjectAlignmentInBytes}
\]

| Object alignment | Phạm vi biểu diễn lý thuyết theo công thức |
|---:|---:|
| 8 byte (mặc định) | khoảng 32 GB |
| 16 byte | khoảng 64 GB |
| 32 byte | khoảng 128 GB |
| 64 byte | khoảng 256 GB |

Đây là phạm vi địa chỉ lý thuyết từ encoding, không phải khuyến nghị đặt heap đúng bằng con số đó. Khả năng cấp phát còn phụ thuộc nền tảng, cách JVM đặt heap và các giới hạn runtime.

### 4.2. Alignment lớn có thể làm mất lợi ích bộ nhớ

Tăng alignment có thể giúp compressed oops biểu diễn heap lớn hơn, nhưng object nhỏ có thể phải chịu nhiều padding hơn. Nếu workload có hàng triệu object nhỏ, padding tăng thêm có thể triệt tiêu một phần lợi ích của compact header.

Không tăng `ObjectAlignmentInBytes` chỉ để vượt giới hạn compressed oops mà chưa benchmark. Hãy đo đồng thời:

- Kích thước object sau alignment.
- Live heap và allocation rate.
- Tỷ lệ object nhỏ so với object lớn.
- GC frequency, pause time và throughput.
- Mức memory sử dụng thực tế trong container.

### 4.3. Không nhầm object alignment với field alignment

Field `long` hoặc `double` có yêu cầu layout riêng; JVM có thể đặt field theo natural alignment và chèn padding giữa các field. `ObjectAlignmentInBytes` nói về alignment của object trong heap, không phải một chỉ thị cho lập trình viên tùy ý sắp xếp field.

Không thêm field giả hoặc thay thứ tự field trong class chỉ để “ép” compact header. Hãy để HotSpot quyết định layout, sau đó quan sát bằng công cụ đo phù hợp.

## 5. Compressed oops và compressed class pointers là hai khái niệm khác nhau

Hai loại pointer đều có chữ “compressed” nhưng trỏ tới hai loại dữ liệu khác nhau:

| Khái niệm | Trỏ tới | Mục đích |
|---|---|---|
| **Compressed ordinary object pointers (compressed oops)** | Object khác trên Java heap | Lưu reference gọn hơn con trỏ native 64-bit |
| **Compressed class pointers** | Metadata class (`Klass`) do HotSpot quản lý | Lưu class identity trong object header bằng encoding nhỏ hơn |
| **Compact Object Headers** | Bố cục header của object | Gộp metadata class và mark/GC/lock trong 64 bit |

Ví dụ:

```java
final class Order {
    Customer customer;
    Address shippingAddress;
}
```

`customer` và `shippingAddress` là reference tới object trên heap. Đây là loại tham chiếu có thể được biểu diễn bằng compressed oops.

Metadata xác định object thuộc class `Order` là class pointer do JVM quản lý. Nó thuộc nhóm compressed class pointer, không phải compressed oop của field `customer`.

### 5.1. Compact header cần compressed class pointer

Compact Object Headers đưa class pointer vào chung vùng 64-bit. HotSpot dùng compressed class pointer encoding với số bit dành cho class identity nhỏ hơn layout truyền thống; tài liệu JDK 25 nêu giới hạn khoảng **4 triệu class khác nhau được load** khi bật tính năng.

Giới hạn này hiếm gặp ở phần lớn ứng dụng server thông thường, nhưng cần đánh giá với hệ thống:

- Sinh rất nhiều class động bằng bytecode generation.
- Dùng nhiều class loader tồn tại đồng thời.
- Có plugin engine hoặc nền tảng triển khai code động.
- Chạy workload tạo class liên tục trong thời gian dài.

Nếu hệ thống có khả năng tiến gần giới hạn class, hãy đo số class loaded/unloaded thực tế và kiểm thử với feature flag trong môi trường đại diện.

### 5.2. Compressed oops không phải điều kiện đồng nghĩa với compact headers

Compressed oops là cơ chế nén reference object; compact header là cách đóng gói metadata đầu object. Hai cơ chế tương tác với nhau trong bố cục heap, nhưng không thể thay tên cho nhau.

JDK 25 có các CDS archive riêng cho cấu hình compact headers có và không có compressed oops. Điều đó phản ánh hai lựa chọn runtime khác nhau; không được suy luận rằng bật compact headers đồng nghĩa compressed oops luôn bật hoặc luôn tắt.

Compressed oops thường được JVM bật tự động khi heap và nền tảng phù hợp. Trước khi can thiệp, kiểm tra flag hiệu lực:

```bash
java -XX:+PrintFlagsFinal -version
```

Không chỉnh các cờ nội bộ về class pointer encoding để cố vượt giới hạn class count. Dùng cấu hình được tài liệu JDK hỗ trợ và xác minh theo đúng build của JVM.

## 6. Tương tác với khóa: `synchronized`, mark word và ObjectMonitorTable

Java object có monitor gắn với object. Khi dùng `synchronized`, JVM quản lý trạng thái khóa; khi nhiều thread tranh chấp hoặc cần các thao tác như `wait()`/`notify()`, JVM có thể chuyển sang monitor đã inflate.

Compact Object Headers thu hẹp header xuống 64 bit nên HotSpot phải quản lý lock state mà vẫn giữ được class metadata, identity hash code và thông tin GC. Trong layout compact, các bit trạng thái khóa nằm trong header; khi cần monitor đã inflate, JVM dùng **ObjectMonitorTable** để tra cứu cấu trúc monitor tương ứng thay vì phải dành một con trỏ monitor đầy đủ trong header.

Ý nghĩa thực tế:

- Các quy tắc đồng bộ hóa của Java không đổi.
- `synchronized`, `wait()`, `notify()` và `notifyAll()` vẫn giữ semantics theo Java Memory Model.
- Header compact vẫn phải biểu diễn lock state và phối hợp với identity hash code.
- Cơ chế monitor nội bộ của HotSpot có thể thay đổi cách tra cứu và quản lý monitor.
- Workload có lock contention cao cần benchmark riêng vì chi phí khóa có thể thay đổi theo đường fast-lock, inflation và tra cứu monitor.

### 6.1. Ví dụ code không cần thay đổi

```java
final class Inventory {
    private int available;

    Inventory(int initial) {
        this.available = initial;
    }

    synchronized boolean reserve(int quantity) {
        if (quantity <= 0 || quantity > available) {
            return false;
        }

        available -= quantity;
        return true;
    }

    synchronized int available() {
        return available;
    }
}
```

Bật compact headers không yêu cầu viết lại `synchronized`. JVM đảm nhiệm layout header và monitor implementation. Không thay `synchronized` bằng một cơ chế khác chỉ vì đã bật compact headers.

### 6.2. Lock không tranh chấp và lock tranh chấp

Một khối `synchronized` ít tranh chấp thường có đường xử lý nhẹ hơn. Khi nhiều thread cùng khóa một object hoặc thread gọi `wait()`, JVM có thể cần monitor đã inflate và quản lý vòng đời monitor.

Compact header giữ ít bit hơn, vì vậy implementation không thể tùy tiện ghi một con trỏ native monitor vào mark word như cách bố trí truyền thống. ObjectMonitorTable là một phần của cơ chế phối hợp đó.

Điều này không có nghĩa mọi lần vào `synchronized` đều phải tra bảng. HotSpot có các đường khóa nhanh và chỉ cần cấu trúc monitor đầy đủ khi điều kiện runtime yêu cầu.

### 6.3. Identity hash code vẫn giữ hợp đồng

```java
Object key = new Object();

int first = System.identityHashCode(key);
int second = System.identityHashCode(key);

assert first == second;
```

Compact headers không thay đổi hợp đồng của `System.identityHashCode`. JVM vẫn phải bảo đảm giá trị identity hash ổn định theo semantics của API trong vòng đời object. Cách lưu trữ và phối hợp giá trị này với lock state là chi tiết nội bộ của HotSpot.

Không đọc trực tiếp mark word bằng `Unsafe` hoặc giả định bit layout cố định. Những giả định như vậy phụ thuộc implementation và có thể hỏng khi đổi JDK, vendor, architecture hoặc flag.

### 6.4. Không lấy benchmark khóa đơn lẻ làm kết luận toàn ứng dụng

Nếu ứng dụng chủ yếu dùng immutable object và ít contention, thay đổi locking có thể hầu như không ảnh hưởng. Nếu workload có nhiều monitor contention, `wait/notify`, hoặc đồng bộ trên object dùng chung, cần benchmark riêng:

- Throughput khi ít tranh chấp.
- Throughput khi tăng số thread tranh chấp.
- Thời gian chờ monitor và p95/p99 latency.
- Số monitor inflation và thời gian giữ lock.
- CPU utilization trong lúc tranh chấp.

JFR có thể giúp quan sát monitor contention; nhưng cần đối chiếu với workload thực tế và không chỉ nhìn một benchmark `synchronized` tổng hợp.

## 7. Tương tác với garbage collector

Header object chứa một số metadata mà GC và runtime cần phối hợp khi đánh dấu, di chuyển hoặc tái sử dụng object. Compact headers phải giữ đủ thông tin cần thiết trong vùng 64-bit nhỏ hơn.

Các nhóm thông tin quan trọng gồm:

- **Object age:** thông tin tuổi object được các generational collectors dùng trong chính sách chuyển object giữa các generation.
- **Forwarding state:** khi collector di chuyển object, runtime cần cách nhận diện object đã được chuyển tới vị trí mới hoặc giữ trạng thái header cần thiết.
- **Class identity:** collector và runtime vẫn cần biết object thuộc class nào.
- **Identity hash code:** giá trị đã được tính phải được bảo toàn qua quá trình di chuyển object.
- **Lock state:** object có thể đang được đồng bộ hoặc có monitor liên quan; GC phải phối hợp với runtime để giữ đúng semantics.

Compact Object Headers không phải một garbage collector mới. Đây là thay đổi bố cục object mà các collector và các đường runtime liên quan phải hiểu.

### 7.1. Generational GC và object age

Các collector generational phân biệt object mới với object sống sót qua nhiều chu kỳ thu gom. Thông tin age hỗ trợ quyết định khi nào object được promote từ young generation sang old generation.

Khi compact header đóng gói metadata, các bit age vẫn phải được biểu diễn. Điều này giúp GC tiếp tục áp dụng chính sách generational mà không yêu cầu ứng dụng thay đổi code.

### 7.2. Moving/compacting GC và forwarding

G1, Parallel và các collector có khả năng di chuyển object cần phối hợp trạng thái header với quá trình copy/evacuation. Khi object được chuyển, runtime phải giữ hoặc khôi phục metadata cần thiết như class identity, identity hash và lock state.

Header nhỏ hơn làm layout và cách dùng bit phức tạp hơn, nhưng việc bảo toàn trạng thái là trách nhiệm của HotSpot. Code ứng dụng không cần tự cập nhật reference khi GC di chuyển object; JVM vẫn bảo đảm reference semantics.

### 7.3. ZGC và các collector khác

Mỗi collector có cách quản lý metadata, relocation và pointer barriers riêng. Không nên suy luận rằng mọi collector đều sử dụng cùng một bit layout hoặc cùng một forwarding path.

Khi triển khai compact headers, kiểm tra đúng tổ hợp:

- JDK vendor và build.
- Garbage collector được chọn.
- Architecture CPU.
- Object alignment.
- JVM options khác có liên quan tới heap và class pointers.

Nếu ứng dụng dùng ZGC hoặc Shenandoah để ưu tiên latency, hãy chạy benchmark với chính collector đó. Không chọn collector chỉ vì compact headers; hai lựa chọn giải quyết hai khía cạnh khác nhau: header thay đổi footprint object, còn collector quyết định chính sách thu gom.

## 8. Tác động tổng hợp tới heap và GC

Giảm header có thể làm giảm số byte sống trên heap, nhưng không nên tự động suy ra GC sẽ giảm pause theo cùng tỷ lệ.

### 8.1. Khi heap footprint giảm

Nếu ứng dụng giữ hàng chục triệu object nhỏ, phần tiết kiệm từ header có thể đáng kể. Với heap limit cố định, live set nhỏ hơn có thể:

- Tăng headroom trước khi heap đạt ngưỡng áp lực.
- Giảm số byte phải copy trong các collection có di chuyển object.
- Tăng số object có thể giữ trong cùng heap.
- Giảm memory bandwidth cần cho một số thao tác quét/copy.
- Cải thiện data locality khi object được đặt gần nhau hơn.

### 8.2. Vì sao GC pause không nhất thiết giảm 4 byte/object?

GC pause phụ thuộc vào nhiều yếu tố: số object, số byte phải scan/copy, reference graph, remembered sets, card tables, mức đồng thời, CPU và cấu hình heap. Compact headers làm giảm metadata trên từng object, nhưng không làm thay đổi toàn bộ chi phí của collector.

Ví dụ, một ứng dụng có phần lớn bộ nhớ nằm trong `byte[]` 10 MB hoặc direct buffers có thể nhận lợi ích header nhỏ. Ngược lại, một cache giữ 30 triệu object `Entry` nhỏ có thể hưởng lợi rõ hơn.

### 8.3. Allocation rate và live set là hai số khác nhau

- **Allocation rate:** lượng byte object được cấp phát mỗi giây.
- **Live set:** lượng dữ liệu còn reachable sau khi GC hoàn tất.
- **Heap occupancy:** dung lượng heap đang được sử dụng tại một thời điểm.
- **RSS/container memory:** bộ nhớ resident mà process chiếm ở cấp hệ điều hành.

Header nhỏ có thể làm allocation bytes và live heap giảm, nhưng RSS không nhất thiết giảm cùng tỷ lệ vì JVM có thể giữ committed heap, code cache, metaspace, thread stacks và native memory. Đo đúng chỉ số cần tối ưu thay vì chỉ nhìn `-Xmx` hoặc RSS.

## 9. Kiểm tra cấu hình thực tế trước khi bật

Trước khi bật compact headers, lưu lại cấu hình runtime đang dùng:

```bash
java -version
java -XX:+PrintFlagsFinal -version
```

Tập trung vào các flag liên quan:

| Flag | Cần hiểu |
|---|---|
| `UseCompactObjectHeaders` | Compact headers có đang được bật không |
| `UseCompressedOops` | Reference tới object trên heap có được nén không |
| `ObjectAlignmentInBytes` | Object alignment hiện tại |
| `UseG1GC`, `UseZGC`, `UseShenandoahGC` | Collector đang được chọn |
| `InitialHeapSize`, `MaxHeapSize` | Heap initial/max thực tế |
| `UseCompressedClassPointers` | Không cấu hình như tuning knob: đã deprecated ở JDK 25 và obsolete/removed ở JDK 27 |

Compact headers dùng compressed class pointer encoding như một phần của layout. Không điều khiển class-pointer mode bằng cờ nội bộ. Trên JDK 27, class pointers luôn được nén; nếu một vendor có backport hoặc thay đổi riêng, kiểm tra release notes của đúng build.

Trên JVM đang chạy, có thể xem flags bằng:

```bash
jcmd <pid> VM.flags -all
```

Nếu chạy trong container, bảo đảm `jcmd` truy cập đúng PID namespace và process. Không dùng output của một JVM developer trên host để suy ra cấu hình JVM trong pod.

## 10. Quan sát object layout bằng Java Object Layout (JOL)

JVM không cung cấp API Java chuẩn để ứng dụng hỏi chính xác kích thước byte của mọi object. Bố cục là chi tiết implementation. Khi cần xem HotSpot layout, có thể dùng **Java Object Layout (JOL)** trong test hoặc diagnostic harness.

Ví dụ:

```java
import org.openjdk.jol.info.ClassLayout;

final class OrderEntry {
    int quantity;
    long productId;
    Object metadata;
}

public class LayoutProbe {
    public static void main(String[] args) {
        OrderEntry entry = new OrderEntry();

        System.out.println(
                ClassLayout.parseInstance(entry).toPrintable());
    }
}
```

Chạy cùng class với hai cấu hình:

```bash
# Header truyền thống theo mặc định JDK 25
java -cp jol-core.jar:app-classes LayoutProbe

# Compact Object Headers
java -XX:+UseCompactObjectHeaders \
     -cp jol-core.jar:app-classes LayoutProbe
```

Trên Windows, classpath dùng dấu `;` thay cho dấu `:`:

```powershell
java -XX:+UseCompactObjectHeaders -cp "jol-core.jar;app-classes" LayoutProbe
```

JOL giúp nhìn thấy header, field offset, alignment gap và instance size theo runtime hiện tại. Kết quả có thể thay đổi theo JDK build, architecture, GC và JVM flags. Đừng đưa số byte do JOL báo thành một hợp đồng API của ứng dụng.

**Lưu ý:** JOL là thư viện bên ngoài; thêm nó vào test/diagnostic scope, không cần đưa vào dependency runtime của service chỉ để bật compact headers.

## 11. Benchmark có kiểm soát trước khi triển khai

Compact Object Headers là một lựa chọn tối ưu layout. Hãy quyết định dựa trên workload, không chỉ dựa vào mức tiết kiệm trung bình 4 byte/object.

### 11.1. Xây dựng baseline và biến thể compact

Giữ cùng JDK 25 vendor/build, artifact, GC, heap, CPU quota, container memory limit, dữ liệu và workload. Chỉ thay đổi cờ compact headers.

```bash
# A. Baseline: compact headers mặc định tắt trong JDK 25
java -Xms4g -Xmx4g \
     -Xlog:gc*:file=gc-baseline.log:time,uptime,level,tags \
     -jar app.jar

# B. Compact Object Headers
java -Xms4g -Xmx4g \
     -XX:+UseCompactObjectHeaders \
     -Xlog:gc*:file=gc-compact.log:time,uptime,level,tags \
     -jar app.jar
```

Nếu production dùng G1, giữ G1 ở cả hai lần chạy. Nếu production dùng ZGC hoặc Shenandoah, lặp lại benchmark với đúng collector đó. Đừng thay đồng thời GC, heap size và object header vì sẽ không biết yếu tố nào tạo ra khác biệt.

### 11.2. Dữ liệu và chỉ số nên thu thập

| Nhóm | Chỉ số | Mục tiêu |
|---|---|---|
| Heap | Live set sau GC, heap used/committed | Xem dữ liệu sống có nhỏ hơn không |
| Allocation | Bytes allocated/second, object allocation count | Xem chi phí cấp phát thay đổi thế nào |
| GC | Frequency, pause, concurrent cycle time, bytes copied | Xem GC có thực sự nhẹ hơn không |
| Hiệu năng | Throughput, p50/p95/p99 latency | Đo tác động người dùng cảm nhận |
| CPU | CPU utilization, cycles/instructions nếu có công cụ | Phát hiện trade-off do layout/locking |
| Đồng bộ | Monitor contention, lock wait time | Phát hiện workload bị ảnh hưởng bởi đường khóa |
| Bộ nhớ process | RSS, committed heap, metaspace, native memory | Phân biệt heap saving với RSS |
| Object layout | Instance size, alignment gap, field offsets | Xác minh class nhỏ có tiết kiệm như kỳ vọng |

Chạy đủ warmup và nhiều lần đo. Luân phiên thứ tự baseline/compact để giảm ảnh hưởng của CPU frequency, cache hệ điều hành và tải máy. Với service, dùng load test có phân phối request và concurrency gần production.

### 11.3. Ví dụ đọc kết quả

Giả sử một service cache dữ liệu giữ 25 triệu `Entry` nhỏ:

| Chỉ số | Baseline | Compact headers |
|---|---:|---:|
| Live heap sau GC | 3,2 GB | 3,08 GB |
| Throughput | 48.000 req/s | 50.500 req/s |
| p99 latency | 42 ms | 39 ms |
| GC pause tổng trong 10 phút | 1,8 s | 1,6 s |
| RSS | 4,1 GB | 4,0 GB |

Đây là **số liệu giả định để minh họa**, không phải kết quả benchmark cam kết của JDK 25. Nó cho thấy cùng một thay đổi có thể tác động đồng thời tới live heap, throughput và latency, nhưng tỷ lệ cải thiện không bằng nhau.

Nếu heap giảm mà throughput không đổi, tính năng vẫn có thể có giá trị về mật độ triển khai. Nếu throughput tăng nhưng p99 xấu đi, cần xem xét mục tiêu SLO và mức biến động. Không quyết định chỉ từ một chỉ số.

### 11.4. Cân nhắc heap sizing sau khi bật

Không giảm `-Xmx` ngay khi thấy heap footprint thấp hơn trong một lần test. Trước tiên kiểm tra:

- Live set ở peak workload.
- Allocation spikes và headroom trước GC.
- Burst traffic và số request đồng thời.
- Native memory, thread stacks và direct buffers.
- Container memory limit và nguy cơ OOM ở cấp hệ điều hành.

Sau khi có dữ liệu ổn định, mới thử giảm heap theo từng bước và benchmark lại. Mục tiêu là giảm tổng tài nguyên mà vẫn giữ SLO và khoảng an toàn vận hành.

## 12. Khi nào compact headers có giá trị rõ?

| Kiểu workload | Khả năng hưởng lợi | Lý do |
|---|---|---|
| Cache giữ hàng chục triệu object nhỏ | Cao hơn | Header chiếm tỷ trọng đáng kể trong mỗi entry |
| Graph, AST, tree hoặc object model nhiều node | Cao hơn | Có nhiều object nhỏ được liên kết với nhau |
| Deserialization tạo nhiều DTO/record | Có thể cao | Object count lớn và allocation dày |
| Messaging pipeline tạo nhiều wrapper/event | Có thể cao | Nhiều object ngắn hạn hoặc sống qua một số GC |
| Ứng dụng chủ yếu xử lý `byte[]`/primitive arrays lớn | Thường thấp hơn | Payload chiếm phần lớn dung lượng |
| Ứng dụng dùng direct/off-heap buffers | Thấp hơn | Dữ liệu chính không nằm trong object header heap |
| Service ít object, ít heap pressure | Thường thấp | Header chỉ chiếm phần nhỏ |
| Workload nhiều monitor contention | Cần đo kỹ | Lock implementation và contention có thể ảnh hưởng |
| Ứng dụng sinh class động cực lớn | Cần kiểm tra giới hạn | Compact class pointer có giới hạn class count |

### 12.1. Tác động tới mật độ triển khai

Nếu một pod giữ nhiều object nhỏ và compact headers giảm live heap, có thể chạy cùng workload với heap nhỏ hơn hoặc tăng số pod trên cùng node. Tuy nhiên, memory request/limit của container còn bao gồm:

- Java heap committed.
- Metaspace và compressed class space.
- Code cache.
- Thread stacks.
- Direct buffers và native allocations.
- JVM, agent và thư viện native.

Đừng giảm Kubernetes memory limit theo đúng phần trăm heap saving. Hãy đo RSS và peak memory của process trong điều kiện tải cao.

## 13. Những điều không thay đổi và giới hạn cần nhớ

| Nhận định | Thực tế |
|---|---|
| Compact headers thay đổi Java object model | Thay đổi layout nội bộ của HotSpot; Java source/API không đổi |
| Mọi object đều nhỏ hơn đúng 4 byte | Tài liệu nêu mức trung bình; padding và field layout quyết định mức thực tế |
| Bật compact headers làm compressed oops tự tắt | Không đúng; hai cơ chế khác nhau |
| Bật compact headers làm GC tự động nhanh hơn | Có thể giảm dữ liệu heap; pause/throughput còn phụ thuộc collector và workload |
| `synchronized` không còn hoạt động như cũ | Semantics Java vẫn giữ nguyên; HotSpot thay đổi chi tiết quản lý monitor |
| Compact headers luôn nhanh hơn | Không bảo đảm; benchmark workload thực tế |
| Cần sửa code để tương thích | Thông thường không cần; chỉ rà soát code phụ thuộc layout nội bộ/Unsafe/agent |
| Đây là Java API portable giữa mọi JVM | Không; đây là tùy chọn HotSpot, cần kiểm tra vendor/runtime |

### 13.1. Tương thích với thư viện native và tooling

Ứng dụng Java thông thường không nhìn thấy header object. Nhưng một số công cụ có thể đọc layout nội bộ:

- Java agents hoặc native agents dùng JVMTI.
- Công cụ heap inspection, debugger hoặc Serviceability Agent.
- Code nội bộ dùng `Unsafe` hoặc native code dựa vào offset layout.
- Profiler hoặc instrumentation can thiệp vào object header.

Các công cụ này cần tương thích với JDK 25 và cấu hình compact headers. Không giả định một agent cũ hỗ trợ layout mới chỉ vì nó chạy được trên cùng major version.

### 13.2. Không tự thao tác mark word

Mark word là chi tiết nội bộ của HotSpot, không phải field Java có thể truy cập. Không dùng `Unsafe` hoặc native pointer arithmetic để sửa lock bits, age, identity hash hay forwarding metadata. Thao tác đó có thể làm hỏng heap, gây crash hoặc phá semantics đồng bộ hóa.

## 14. Sự cố thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| JVM báo unrecognized option | Runtime không phải HotSpot build hỗ trợ flag hoặc dùng JDK sai | Kiểm tra `java -version`, vendor và `java -XX:+PrintFlagsFinal -version` |
| Thêm `UnlockExperimentalVMOptions` nhưng không cần | Sao chép hướng dẫn JDK 24 | Với JDK 25, dùng trực tiếp `-XX:+UseCompactObjectHeaders` |
| Flag có trong script nhưng runtime vẫn false | Script không chạy JVM mong muốn hoặc option bị ghi đè | Kiểm tra command line và `jcmd <pid> VM.flags -all` |
| Heap giảm ít hơn dự kiến | Workload có ít object nhỏ, nhiều array/direct buffer hoặc padding | Dùng JOL, heap histogram và allocation profile |
| Heap giảm nhưng RSS gần như không đổi | Heap committed vẫn giữ, native memory chiếm tỷ trọng lớn | Đo heap, metaspace, thread stacks, direct memory và RSS riêng |
| Throughput giảm ở workload khóa | Contention/monitor management thay đổi | Benchmark lock contention, kiểm tra JFR monitor events |
| p99 tăng nhưng average giảm | Một số đường đồng bộ hoặc allocation outlier bị ảnh hưởng | So sánh p95/p99, thread states, GC và lock waits |
| Lỗi với công cụ heap/profiler cũ | Agent dựa vào layout object truyền thống | Nâng cấp agent/tool, thử lại với compact headers |
| Class loading động chạm giới hạn | Class count tiến gần giới hạn encoding | Đo class loaded/unloaded và đánh giá thiết kế class loader |
| Tăng alignment nhưng heap không giảm | Padding cuối object tăng | Trở lại alignment mặc định và so sánh layout |

### Trình tự chẩn đoán

1. Xác nhận đúng JDK 25 HotSpot vendor/build.
2. Xác nhận `UseCompactObjectHeaders` thực sự là `true`.
3. Ghi lại compressed oops, object alignment, GC và heap flags.
4. Dùng JOL hoặc heap histogram để xác định class nào chiếm nhiều object.
5. Đo live heap và allocation rate trước/sau.
6. Nếu có regression, kiểm tra lock contention, GC behavior và agent.
7. Tắt compact headers trong một lần chạy đối chứng để xác định regression có liên quan tới layout mới không.

## 15. Bài tập thực hành và tiêu chí hoàn thành

### Bài tập 1 — Tính phần heap có thể tiết kiệm

Một service giữ 18 triệu object nhỏ và giả định mức giảm trung bình 4 byte/object. Tính lượng byte/MB lý thuyết có thể tiết kiệm. Vì sao không được dùng kết quả đó làm cam kết giảm RSS?

### Bài tập 2 — Phân biệt hai loại compressed pointer

Một class có hai field `Customer customer` và `Address address`. Giải thích hai field này liên quan compressed oops thế nào và class pointer trong header khác gì.

### Bài tập 3 — Chọn object alignment

Một ứng dụng cần heap lớn hơn 32 GB và đang xem xét tăng `ObjectAlignmentInBytes` từ 8 lên 16. Hãy giải thích phạm vi compressed oop tăng ra sao, đổi lại có thể mất bao nhiêu memory do padding và cần đo những gì.

### Bài tập 4 — Lock contention

Một service có nhiều thread gọi `synchronized` trên cùng một object. Hãy đề xuất benchmark so sánh compact headers và baseline, gồm throughput, monitor wait time, p99 và CPU. Vì sao không thể kết luận chỉ từ một benchmark lock không tranh chấp?

### Bài tập 5 — Tương tác GC

Một cache giữ 30 triệu object nhỏ sống qua nhiều young GC. Giải thích object age và forwarding state có vai trò gì trong runtime; vì sao giảm header có thể giảm heap nhưng không đảm bảo pause time giảm cùng tỷ lệ?

### Bài tập 6 — Kiểm chứng trên JDK 25

Viết hai lệnh chạy cùng ứng dụng với cùng `-Xms`/`-Xmx`, một baseline và một bật compact headers. Nêu cách xác nhận flag hiệu lực và tối thiểu năm chỉ số cần thu thập.

### Tiêu chí đạt

Bạn hoàn thành bài học khi có thể:

1. Giải thích vì sao header truyền thống chiếm 96 hoặc 128 bit và compact header giảm xuống 64 bit.
    2. Nêu đúng trạng thái theo phiên bản: JDK 25 có JEP 519 là product feature nhưng mặc định tắt; JDK 27 bật compact headers mặc định qua JEP 534.
3. Phân biệt object alignment, compressed oops và compressed class pointers.
4. Giải thích mối liên hệ giữa alignment, compressed oop address range và padding.
5. Nhận diện giới hạn khoảng 4 triệu class được load khi compact header bật.
6. Giải thích tác động tới mark word, `synchronized`, monitor inflation và ObjectMonitorTable ở mức runtime.
7. Mô tả metadata object age, forwarding, class identity và identity hash mà GC/runtime phải giữ.
8. Dùng `PrintFlagsFinal`, `jcmd` và JOL để xác minh cấu hình/layout.
9. Thiết kế benchmark có baseline, giữ nguyên workload và đo cả heap, GC, latency, throughput lẫn RSS.
10. Không coi compact headers là GC mới, API Java portable hoặc tối ưu luôn có lợi.

### Tài liệu tham khảo

1. [JEP 519 — Compact Object Headers](https://openjdk.org/jeps/519): chuyển Compact Object Headers thành product feature trong JDK 25.
2. [JEP 450 — Compact Object Headers (Experimental)](https://openjdk.org/jeps/450): bối cảnh thiết kế và thử nghiệm ban đầu ở JDK 24.
3. [Oracle JDK 25 — The `java` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `UseCompactObjectHeaders`, compressed oops và `ObjectAlignmentInBytes`.
4. [Oracle JDK 25 — Garbage Collection Tuning Guide, Other Considerations](https://docs.oracle.com/en/java/javase/25/gctuning/other-considerations.html): kích thước compact header, class-count limit và metadata liên quan.
5. [Oracle JDK 25 — HotSpot Performance Enhancements](https://docs.oracle.com/en/java/javase/25/vm/java-hotspot-virtual-machine-performance-enhancements.html): compressed ordinary object pointers và cách giải mã offset.
6. [OpenJDK — ObjectMonitorTable](https://wiki.openjdk.org/display/HotSpot/ObjectMonitorTable): thiết kế bảng monitor và quản lý monitor nội bộ.
7. [Java Object Layout (JOL)](https://openjdk.org/projects/code-tools/jol/): công cụ quan sát object layout của JVM.
8. [Oracle JDK 27 — Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): compact headers bật mặc định qua JEP 534 và `UseCompressedClassPointers` bị loại bỏ.

> **Ghi chú hiện hành:** JDK 25 đưa Compact Object Headers thành product feature nhưng vẫn tắt mặc định; JDK 27 bật layout này mặc định. Khi benchmark trên JDK 27, phải tắt rõ ràng bằng `-XX:-UseCompactObjectHeaders` nếu cần baseline header cũ. Không dùng `UseCompressedClassPointers` đã bị loại bỏ, không dùng bit layout nội bộ như API, không phụ thuộc biased locking hoặc stack-locking từ tài liệu cũ, và luôn benchmark đúng JDK vendor/build, GC, alignment và workload trước khi triển khai.
