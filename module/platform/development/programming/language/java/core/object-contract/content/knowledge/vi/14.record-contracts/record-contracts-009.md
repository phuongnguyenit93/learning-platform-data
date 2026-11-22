# Không dựa vào thuật toán hash hoặc định dạng `toString()` được sinh như một giao thức cố định

## Mục tiêu bài học

Một khai báo `record` trong Java tự cung cấp các phương thức `equals(Object)`, `hashCode()` và `toString()` nếu lập trình viên không tự khai báo chúng. Những phương thức này rất hữu ích khi làm việc với **đối tượng mang dữ liệu**: so sánh các thành phần, dùng làm khóa trong collection và đọc nhanh trạng thái khi gỡ lỗi.

Nhưng **hợp đồng hành vi** không đồng nghĩa với **cam kết giữ nguyên chi tiết triển khai hoặc văn bản đầu ra**. Với các phương thức được sinh tự động, Java bảo đảm những thuộc tính quan trọng; Java không hứa một công thức hash số học cụ thể hoặc một chuỗi `toString()` có thể xem như định dạng trao đổi dữ liệu lâu dài.

Sau bài học, bạn có thể:

- Nêu phần được bảo đảm và phần không được bảo đảm của `equals()`, `hashCode()` và `toString()` tự sinh cho `record`.
- Tránh lưu `hashCode()` như định danh, checksum hay khóa liên kết bền vững giữa các lần chạy.
- Tránh parse `toString()` tự sinh để phục hồi record hoặc dùng nó như JSON, CSV, thông điệp API hay định dạng lưu trữ.
- Thiết kế codec có phiên bản rõ ràng khi cần một định dạng dữ liệu ổn định.
- Viết kiểm thử hướng vào hợp đồng, đồng thời hiểu các bẫy với component là mảng hoặc đối tượng có thể thay đổi.

## 1. Điều gì được sinh từ một khai báo record?

Ví dụ Java 17+:

```java
record Event(int id, String action) {}
```

Khai báo trên tạo một kiểu record có hai component, mỗi component gắn với một trường `private final` và accessor tương ứng `id()`, `action()`. Ngoài constructor chuẩn, record có các phương thức `equals(Object)`, `hashCode()` và `toString()` nếu chưa được cài đặt tường minh.

Bạn có thể viết:

```java
Event a = new Event(42, "LOGIN");
Event b = new Event(42, "LOGIN");
Event c = new Event(43, "LOGIN");

System.out.println(a.equals(b));                // true
System.out.println(a.hashCode() == b.hashCode()); // true
System.out.println(a.equals(c));                // false
```

Đây là những đoạn mã minh họa cần đặt trong phương thức có thể truy cập `Event`; chương trình độc lập nằm ở phần sau.

**Hợp đồng quan trọng:**

- Phương thức `equals()` tự sinh kiểm tra đối số là instance của **cùng lớp record** và các component tương ứng bằng nhau theo quy tắc của từng kiểu component. Với component kiểu tham chiếu, quy tắc tương đương `Objects.equals(...)`; với kiểu nguyên thủy, dùng ngữ nghĩa so sánh phù hợp với wrapper tương ứng.
- Nếu `a.equals(b)` là `true`, `a.hashCode()` và `b.hashCode()` **phải bằng nhau** khi dữ liệu liên quan không thay đổi.
- `toString()` tự sinh là biểu diễn dễ đọc, bao gồm tên lớp record, tên các component và biểu diễn chuỗi của giá trị component. **Cú pháp chính xác không được chốt làm giao thức.**

Hai record có cùng dữ liệu có thể in ra văn bản giống nhau nhưng điều đó không biến văn bản ấy thành một định dạng lưu trữ chính thức. Khả năng so sánh theo component và khả năng đọc một chuỗi hiển thị là hai nhu cầu khác nhau.

## 2. Bảo đảm ngữ nghĩa khác bảo đảm thuật toán

Để phân biệt chính xác, xem bảng sau:

| Khía cạnh | Điều có thể dựa vào | Điều không nên giả định |
| --- | --- | --- |
| `equals()` tự sinh | Cùng lớp record, component tương ứng bằng nhau thì record bằng nhau | Mã máy, thứ tự kiểm tra hoặc thuật toán so sánh nội bộ cố định |
| `hashCode()` tự sinh | Hash được dẫn xuất từ các component; record bằng nhau phải có cùng hash | Một công thức số học, thứ tự kết hợp, giá trị `int` cố định qua các môi trường |
| `toString()` tự sinh | Biểu diễn có tên record, tên component và chuỗi giá trị component | Dấu ngoặc, dấu phẩy, dấu bằng, khoảng trắng, escape hay bố cục ký tự cố định |
| Accessor như `id()` | Lấy giá trị component theo kiểu đã khai báo | Đây tự động là định dạng serialization có phiên bản |

Điều này đặc biệt quan trọng khi nâng cấp JDK: hai bản Java có thể cùng tuân thủ đầy đủ hợp đồng `Record` nhưng vẫn chọn thuật toán tạo hash hoặc trình bày `toString()` khác nhau.

Java API mô tả rõ rằng **thuật toán hash chính xác của record là không xác định ở mức đặc tả và có thể thay đổi**, kể cả số hash của cùng dữ liệu giữa các lần thực thi. Với `toString()`, API cũng nói **định dạng chính xác có thể đổi và chương trình không nên phân tích chuỗi ấy để khôi phục component**.

Vì thế, kiểm thử đúng nên khẳng định **quan hệ và hành vi**, không khóa chặt vào chi tiết mà nền tảng không cam kết.

## 3. Không coi `record.hashCode()` là một mã định danh ổn định

Hãy xét:

```java
record Order(int orderId, String status) {}
```

Trong bộ nhớ, `hashCode()` rất hữu ích cho `HashMap<Order, ...>` hoặc `HashSet<Order>` khi component giữ trạng thái phù hợp với hợp đồng.

Tuy nhiên, những cách sử dụng sau không an toàn:

- Ghi `order.hashCode()` vào cơ sở dữ liệu và coi nó là khóa chính của đơn hàng.
- Gửi hash sang một dịch vụ khác làm mã tham chiếu để dịch vụ ấy tự tính lại từ record.
- Dùng mã hash làm tên tệp cache bền vững mà cần tồn tại đúng qua nâng cấp JDK hay chạy ứng dụng lần khác.
- So sánh hash của record ở hai JVM hoặc hai bản triển khai như một chứng cứ bắt buộc về dữ liệu giống nhau.
- Coi một hash 32 bit là checksum đủ mạnh, chữ ký số, bằng chứng toàn vẹn hoặc token bảo mật.

Có hai lý do độc lập.

### 3.1. Thuật toán không phải hợp đồng công khai

Java chỉ yêu cầu mã băm được xây dựng phù hợp từ các component và tuân thủ hợp đồng của `Object.hashCode()`. Không có nghĩa compiler phải sử dụng công thức giống `Objects.hash(id, status)`, `31 * id + status.hashCode()` hay bất kỳ công thức giả định nào.

Mã nguồn như sau là phản mẫu:

```java
Order order = new Order(10, "PAID");

// Không lưu cố định order.hashCode() thành khóa giao thức.
// Không kiểm thử rằng order.hashCode() phải bằng một số nguyên đoán trước.
int implementationHash = order.hashCode();
```

Kết quả `implementationHash` là một `int` hợp lệ, nhưng từ một giá trị quan sát được ở một JDK không được kết luận rằng mọi phiên bản đều phải cho cùng số.

Một số component còn có cách tính mã băm phụ thuộc đối tượng chứa bên trong: nếu component là mảng hoặc một kiểu không ghi đè `hashCode()`, hash của component có thể mang tính danh tính đối tượng. Khi đó, hai dữ liệu “trông giống nhau” chưa chắc có hash bằng nhau.

### 3.2. Collision luôn có thể xảy ra

`hashCode()` trả về `int` 32 bit. Nhiều record khác nhau có thể có cùng hash. Hợp đồng chỉ bảo đảm chiều:

```text
a.equals(b) == true
           ⇒ a.hashCode() == b.hashCode()
```

Không có chiều đảo ngược:

```text
a.hashCode() == b.hashCode()
           ⇏ a.equals(b) == true
```

Do đó, ngay cả khi bạn tự cố định thuật toán hash, giá trị hash vẫn không tự động trở thành ID duy nhất. Một hệ thống cần định danh ổn định nên có **ID nghiệp vụ rõ ràng**, chẳng hạn `orderId` được quản lý theo yêu cầu hệ thống; việc tạo ID và bảo đảm duy nhất là một phần thiết kế dữ liệu riêng.

Nếu thực sự cần khóa tra cứu bền vững từ nội dung, phải định nghĩa **định dạng byte chuẩn hóa** và chiến lược định danh/hash dành cho mục đích đó. Một mã băm nhanh cho collection không thay thế cho định danh hay hàm mật mã.

## 4. Không coi `record.toString()` tự sinh là JSON, CSV hoặc wire protocol

Với:

```java
record Order(int id, String status) {}
Order order = new Order(10, "PAID");
System.out.println(order);
```

Một bản JDK hiện hành có thể hiển thị dạng tương tự:

```text
Order[id=10, status=PAID]
```

**Dòng trên chỉ minh họa cách hiển thị phổ biến, không phải đầu ra ký tự được Java bảo đảm cho mọi phiên bản.** Không viết parser hay test bắt buộc khớp dấu `[`, `]`, dấu `=`, dấu phẩy hoặc khoảng trắng của mẫu hiển thị này.

Ví dụ sau là **phản mẫu**:

```java
String display = order.toString();

// SAI: cố parse display dựa trên dấu ',' hoặc '=' của toString tự sinh.
// SAI: gửi display như JSON/CSV hoặc khẳng định nó có schema cố định.
// SAI: lưu display vào DB rồi dùng split(...) để dựng lại Order.
```

Các vấn đề điển hình:

1. **Cú pháp không được cố định.** Java có thể thay đổi cách sắp xếp ký tự, ký hiệu và chi tiết hiển thị khi vẫn thỏa hợp đồng `toString()`.
2. **Giá trị component không tự được escape theo một giao thức bạn chọn.** Ví dụ chuỗi chứa dấu phẩy, xuống dòng, dấu ngoặc hay `=` làm parser dựa vào dấu phân cách trở nên mong manh.
3. **Giá trị lồng nhau có thể không phải dữ liệu có thể khôi phục.** Nếu component là mảng, `toString()` của chính mảng không tự in một cấu trúc dữ liệu kiểu JSON; một số giá trị component có thể dùng định dạng phục vụ debug.
4. **Thông tin nhạy cảm có thể xuất hiện trong log.** Một record chứa token, email hoặc bí mật có thể để lộ nội dung nếu in mặc định mà không kiểm soát.

`toString()` rất hữu ích để đọc nhanh trạng thái trong quá trình phát triển. Nếu cần một biểu diễn hiển thị cố định trong UI, hãy có formatter riêng. Nếu cần gửi hoặc lưu dữ liệu, dùng **serialization format với schema rõ ràng**.

## 5. Ví dụ Java 17+ hoàn chỉnh: so sánh hợp đồng và định dạng có phiên bản

Chương trình này dùng record `Event` và cố ý **không** dựa vào số hash hay chuỗi `toString()` được sinh tự động để mã hóa dữ liệu.

Để có ví dụ độc lập không phụ thuộc thư viện JSON bên ngoài, ta định nghĩa một codec rất nhỏ:

- Tiền tố `v1` xác định phiên bản định dạng.
- `id` là số nguyên thập phân.
- `action` được mã hóa UTF-8 rồi Base64 URL-safe không padding, nên bản thân trường này không chứa ký tự `|`.

Định dạng chỉ dành cho ví dụ; trong hệ thống thật, JSON/CBOR/Protobuf hoặc một chuẩn có schema và quy tắc escaping phù hợp thường tiện hơn.

Lưu tệp `RecordProtocolDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Objects;

public class RecordProtocolDemo {
    record Event(int id, String action) {
        Event {
            Objects.requireNonNull(action, "action");
        }
    }

    static String encode(Event event) {
        String payload = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(
                        event.action().getBytes(StandardCharsets.UTF_8));
        return "v1|" + event.id() + "|" + payload;
    }

    static Event decode(String wire) {
        String[] parts = wire.split("\\|", -1);
        if (parts.length != 3 || !"v1".equals(parts[0])) {
            throw new IllegalArgumentException("Unsupported wire format");
        }

        int id = Integer.parseInt(parts[1]);
        String action = new String(
                Base64.getUrlDecoder().decode(parts[2]),
                StandardCharsets.UTF_8);
        return new Event(id, action);
    }

    public static void main(String[] args) {
        Event a = new Event(42, "LOGIN");
        Event b = new Event(42, "LOGIN");
        Event c = new Event(43, "LOGIN");

        System.out.println("equal records: " + a.equals(b));
        System.out.println("equal hash contract: "
                + (a.hashCode() == b.hashCode()));
        System.out.println("different records: " + !a.equals(c));

        String wire = encode(a);
        System.out.println("wire: " + wire);
        System.out.println("round trip: " + decode(wire).equals(a));

        // Không dựa vào chữ số hash hoặc định dạng toString().
        System.out.println("debug text available: "
                + !a.toString().isBlank());
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac RecordProtocolDemo.java
java RecordProtocolDemo
```

**Đầu ra xác định của chính chương trình:**

```text
equal records: true
equal hash contract: true
different records: true
wire: v1|42|TE9HSU4
round trip: true
debug text available: true
```

Giải thích:

- `a.equals(b)` là `true` vì cùng lớp `Event` và component tương ứng bằng nhau.
- Mã băm của `a` và `b` bắt buộc bằng nhau theo hợp đồng; ta **chỉ kiểm tra bằng nhau**, không in và không khẳng định một số hash cụ thể.
- `a` và `c` có `id` khác nhau nên không bằng nhau.
- `wire` được tạo theo quy tắc do chính chương trình định nghĩa. Chuỗi `LOGIN` mã hóa Base64 URL-safe thành `TE9HSU4`, do đó biểu diễn `v1|42|TE9HSU4` là dự đoán được.
- `decode(wire)` khôi phục các trường qua codec có phiên bản, không parse `Event.toString()`.
- `toString()` vẫn dùng được cho mục đích hiển thị; chương trình chỉ xác minh có chuỗi thông tin, không buộc nó theo cú pháp hiển thị cụ thể.

Codec ví dụ này còn đơn giản: `decode` dùng bộ giải mã UTF-8 mặc định và không định nghĩa đầy đủ các quy tắc kiểm tra dữ liệu độc hại, giới hạn kích thước, schema tiến hóa hoặc tương thích ngược. Trong một giao thức thật, cần bổ sung các ràng buộc ấy và kiểm thử dữ liệu lỗi. Nhưng nó đã thể hiện nguyên tắc quan trọng: **định dạng trao đổi nằm trong hợp đồng do ứng dụng kiểm soát**.

## 6. Viết kiểm thử đúng trọng tâm

Một kiểm thử tốt cho record tự sinh nên kiểm tra các thuộc tính mà Java bảo đảm:

```java
Event x = new Event(7, "READY");
Event y = new Event(7, "READY");
Event z = new Event(8, "READY");

// Kiểm tra hợp đồng semantic:
boolean sameValue = x.equals(y);                 // true
boolean equalHash = x.hashCode() == y.hashCode(); // true
boolean different = !x.equals(z);                // true
boolean noNullEquality = !x.equals(null);        // true

// Kiểm tra format do chính chương trình định nghĩa:
boolean codecRoundTrip = decode(encode(x)).equals(x); // true
boolean schemaVersion = encode(x).startsWith("v1|");  // true
```

Đây là **đoạn mã minh họa trong lớp `RecordProtocolDemo`**, sử dụng `Event` và `encode/decode` ở ví dụ hoàn chỉnh.

Các kiểu assertion không nên viết:

```java
// PHẢN MẪU:
// assertEquals(12345678, x.hashCode());
// assertEquals("Event[id=7, action=READY]", x.toString());
```

Hai assertion trên ràng buộc code vào các chi tiết không phải hợp đồng bắt buộc của việc tự sinh. Chúng có thể vô tình đúng trên JVM hiện tại rồi trở nên không bền vững khi thay đổi triển khai.

Nếu bạn **tự định nghĩa** một formatter hoặc codec nhằm cung cấp đầu ra cụ thể, kiểm thử chính xác chuỗi/byte do formatter hoặc codec đó tạo ra là hợp lý. Phải phân biệt:

- **Kiểm thử contract của Java record:** ngữ nghĩa `equals` và quan hệ với `hashCode`, thông tin có mặt trong biểu diễn `toString`.
- **Kiểm thử contract của ứng dụng:** chuỗi/byte chính xác của một codec hay formatter được ứng dụng cam kết, bao gồm phiên bản và xử lý ký tự đặc biệt.

Khi sản phẩm yêu cầu lưu trữ bền vững, hãy thêm golden test cho codec ứng dụng qua các phiên bản của phần mềm; golden test như vậy thuộc trách nhiệm của schema ứng dụng, không phải nhiệm vụ của `record.toString()`.

## 7. Điểm dễ bỏ sót: component là mảng hoặc đối tượng mutable

`record` là **shallowly immutable**: tham chiếu component không thể được gán lại từ bên ngoài, nhưng nội dung của đối tượng mà component trỏ đến vẫn có thể thay đổi.

Ví dụ:

```java
record Packet(byte[] data) {}

Packet first = new Packet(new byte[] {1, 2});
Packet second = new Packet(new byte[] {1, 2});

System.out.println(first.equals(second)); // false
```

Đây là đoạn minh họa bên trong phương thức. Mặc dù hai mảng `byte[]` có nội dung giống nhau, record tự sinh dùng quy tắc bằng nhau của **component kiểu tham chiếu**. Mảng không ghi đè `Object.equals()` để so theo phần tử, vì vậy hai mảng riêng biệt không bằng nhau theo tham chiếu.

Tương tự, hash của record có component mảng sẽ dựa trên hash của component mảng, không mặc nhiên tính `Arrays.hashCode(data)` hoặc `Arrays.deepHashCode(data)`. `toString()` tự sinh có thể chứa biểu diễn của mảng mang tính danh tính, không phải danh sách byte để parse.

Một sai lầm khác là kỳ vọng `final` trên component giúp nội dung bên trong hoàn toàn bất biến. Đoạn sau vẫn sửa được mảng:

```java
byte[] bytes = {1, 2};
Packet packet = new Packet(bytes);
bytes[0] = 9;                    // Mảng ban đầu bị sửa
packet.data()[1] = 8;            // Accessor trả về tham chiếu mảng
```

Điều này không nhất thiết làm hash của record mảng thay đổi theo nội dung mảng, bởi hash mảng mặc định dựa trên danh tính; nhưng nó minh họa lý do **record không tự là một giá trị bất biến sâu**. Với các kiểu component mutable khác có `equals/hashCode` dựa trên trạng thái bên trong, sửa trạng thái có thể làm thay đổi kết quả của `equals/hashCode` trong khi đối tượng đang nằm trong `HashMap` hoặc `HashSet`.

Nếu nghiệp vụ cần so sánh mảng theo giá trị, hãy định nghĩa rõ phép so và phép băm tương ứng bằng `Arrays.equals/hashCode` hoặc `Arrays.deepEquals/deepHashCode`, đồng thời cân nhắc **defensive copy** trong constructor/accessor. Đó là một thiết kế riêng: không thể suy ra từ việc record tự sinh phương thức.

## 8. Giao thức ổn định cần quyết định rõ điều gì?

Khi record là DTO hoặc mô hình ứng dụng tham gia API, sự tồn tại của record không quyết định thay cho schema bên ngoài. Một giao thức lâu dài cần ít nhất:

1. **Tên trường và kiểu dữ liệu:** ví dụ `id` là số nguyên, `action` là chuỗi UTF-8; dữ liệu nào là bắt buộc, dữ liệu nào có thể `null`.
2. **Cấu trúc và encoding:** JSON, CBOR, Protobuf hoặc format có đặc tả; nếu là chuỗi tự định nghĩa, phải chỉ rõ escaping/delimiter/độ dài trường.
3. **Phiên bản và tương thích:** thêm trường, đổi tên, đổi kiểu, xử lý trường không biết hoặc giá trị thiếu như thế nào.
4. **Quy tắc chuẩn hóa:** thứ tự trường nếu cần, số thực, timezone, locale, ký tự Unicode, khoảng trắng, encoding và các trường hợp biên.
5. **Kiểm tra đầu vào:** giới hạn độ dài, giá trị hợp lệ, dữ liệu lỗi, phiên bản không được hỗ trợ.
6. **Tách biệt định danh và checksum:** ID nghiệp vụ, content digest hoặc chữ ký số phải được chọn theo yêu cầu, không thay bằng `record.hashCode()`.

Chẳng hạn, record:

```java
record Payment(long id, String currency, long amountMinor) {}
```

có thể ánh xạ sang tài liệu JSON có schema do ứng dụng hoặc thư viện serialization quản lý. Khi cần định dạng JSON ổn định, phải xác định tên các thuộc tính, quy tắc chuỗi, number, versioning, backward compatibility và thư viện/thiết lập serialization. **Không gửi `payment.toString()` và giả định phía nhận có thể diễn giải đó là JSON.**

Có thể tự ghi đè `toString()` để kiểm soát cách trình bày:

```java
record Payment(long id, String currency, long amountMinor) {
    @Override
    public String toString() {
        return "Payment #" + id + " (" + currency + ")";
    }
}
```

Nhưng đây là **định dạng do tác giả ứng dụng định nghĩa**, không phải cú pháp mặc định của record. Nó phù hợp hơn cho thông điệp người đọc; nếu dùng làm giao thức, vẫn cần đặc tả, escaping, phiên bản và quy tắc tương thích. Việc tự ghi đè một phương thức không tự giải quyết các vấn đề của serialization.

## 9. Các lỗi thường gặp

### Lỗi 1 — Gắn chặt test vào số hash cụ thể

Một bản JDK in `hashCode() == 12345` không tạo ra yêu cầu mọi bản JVM phải trả đúng số đó. Kiểm thử **đối tượng bằng nhau thì hash bằng nhau**, không kiểm thử hash cố định do trình biên dịch sinh.

### Lỗi 2 — Dùng hash như khóa chính hoặc mã giao dịch

Hash có thể va chạm và công thức sinh có thể thay đổi. Dùng ID nghiệp vụ ổn định hoặc cơ chế định danh được thiết kế riêng.

### Lỗi 3 — Parse `toString()` bằng `split`

Định dạng `toString()` tự sinh không có cam kết cú pháp ổn định; component có thể chứa dấu phân cách hoặc xuống dòng. Dùng codec/serialization có schema.

### Lỗi 4 — Giả định `toString()` của record là JSON

Biểu diễn gỡ lỗi không đồng nghĩa với JSON. Cú pháp trông gần giống trên một máy không khiến nó thành giao thức được đặc tả.

### Lỗi 5 — Cho rằng record tự sinh phép so sánh sâu

Record kiểm tra component theo quy tắc kiểu component. Mảng có `equals()` theo danh tính, không tự so sâu nội dung. Nếu cần giá trị sâu, phải cài đặt tường minh và giữ hợp đồng `hashCode`.

### Lỗi 6 — Nhầm bất biến của trường với bất biến nội dung

Trường component final không cấm sửa phần tử bên trong một mảng hoặc collection được tham chiếu. Nếu dùng record làm khóa băm, cần xét tính ổn định của dữ liệu tham gia `equals/hashCode`.

### Lỗi 7 — Dùng `toString()` mặc định trong log có dữ liệu nhạy cảm

Biểu diễn mặc định có thể đưa chuỗi của component vào log. Đánh giá trường cần ẩn, chọn logger/formatter phù hợp và không in token hoặc bí mật chỉ vì record tự có `toString()`.

### Lỗi 8 — Cho rằng cách cài đặt hiện hành là một phần của đặc tả

Một hành vi được quan sát trong một phiên bản OpenJDK có thể là chi tiết nội bộ, không phải cam kết tương thích lâu dài. Hãy dựa vào Javadoc/JLS để quyết định điều có thể đưa thành hợp đồng ứng dụng.

## 10. Bài tập tự kiểm tra

Xét record:

```java
record Snapshot(int version, String payload) {}
Snapshot x = new Snapshot(1, "ok");
Snapshot y = new Snapshot(1, "ok");
Snapshot z = new Snapshot(2, "ok");
```

Đây là đoạn mã đặt trong phương thức có thể truy cập `Snapshot`.

Hãy đánh giá các nhận định:

| Nhận định | Đúng/Sai | Lý do |
| --- | --- | --- |
| `x.equals(y)` là `true`. | **Đúng** | Cùng lớp và cùng giá trị component. |
| `x.hashCode() == y.hashCode()` phải là `true`. | **Đúng** | Bảo đảm của hợp đồng hash. |
| `x.hashCode()` phải là một số nguyên cố định trên mọi JDK. | **Sai** | Thuật toán hash của record tự sinh không được cố định. |
| `x.equals(z)` là `false`. | **Đúng** | Component `version` khác. |
| Nếu hash của `x` và `z` trùng nhau thì `x.equals(z)` phải là `true`. | **Sai** | Collision không suy ra equality. |
| Chuỗi `x.toString()` có thể được parse bằng dấu `[`, `,`, `=` và `]` theo đặc tả Java. | **Sai** | Cú pháp chính xác của `toString()` tự sinh không được bảo đảm. |
| Có thể dùng `x.toString()` để quan sát trạng thái khi debug. | **Đúng** | Đây là mục đích phù hợp của biểu diễn dễ đọc. |
| Muốn lưu trữ lâu dài nên xác định format/schema và version thay vì dựa vào `toString()`. | **Đúng** | Ứng dụng kiểm soát hợp đồng dữ liệu của mình. |

Bài tập thực hành: giữ record `Snapshot` nhưng thiết kế một codec `v1` có encoding chuỗi tường minh. Thêm một trường vào record trong phiên bản `v2` và định nghĩa cách bộ đọc `v2` chấp nhận dữ liệu `v1`. Viết test round-trip và test phiên bản cũ. Những bài kiểm tra này nên bảo vệ định dạng **do ứng dụng cam kết**, không bảo vệ số hash hay cú pháp debug do JVM tạo ra.

## 11. Tài liệu chuẩn để đối chiếu

- [Java SE 21 — `java.lang.Record`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html): mô tả trực tiếp hợp đồng và giới hạn của `equals()`, `hashCode()`, `toString()`.
- [Java SE 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html): giải thích các thành viên và phương thức được sinh cho record.

Khi cần biết một hành vi có thể dựa vào lâu dài hay không, ưu tiên **hợp đồng API và Java Language Specification**, thay vì chép lại kết quả của một bản chạy hiện tại rồi xem đó là chuẩn.

## Ghi nhớ

**Với record tự sinh, hãy dựa vào hợp đồng bằng nhau và mã băm, không dựa vào công thức hash hoặc các ký tự chính xác của `toString()`.** Mã băm dành cho các thao tác dựa trên hash trong bộ nhớ; biểu diễn `toString()` dành cho việc đọc và chẩn đoán. Khi cần định dạng ổn định qua phiên bản, máy và tiến trình, hãy thiết kế **schema, codec, encoding và versioning** rõ ràng rồi kiểm thử chính định dạng ấy.