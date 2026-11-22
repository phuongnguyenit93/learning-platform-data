# Thông báo không chỉ ra nơi giá trị `null` được sinh ra — giới hạn của Helpful NullPointerException

## 1. Mục tiêu bài học

Từ Java 14, **Helpful NullPointerExceptions** (JEP 358) giúp JVM mô tả cụ thể hơn một `NullPointerException` (*NPE*) được tạo ra **khi chương trình cố sử dụng một tham chiếu `null`**. Ví dụ, thay vì chỉ biết có NPE trong một dòng có nhiều lời gọi phương thức, JVM có thể chỉ ra thao tác thất bại và biểu thức nào đang có giá trị `null`:

```text
Cannot invoke "String.length()" because "profile.email" is null
```

Nhưng có một giới hạn rất quan trọng:

> **Thông báo helpful NPE mô tả `null` tại điểm nó được sử dụng sai (*dereference site*), không tự truy nguyên đường dữ liệu để tìm nơi giá trị `null` được tạo ra, gán vào field, trả về từ database, cache, API hay một nhánh điều khiển trước đó (*origin site*).**

Nó có thể ghi rằng *“the return value of Customer.address() is null”*, nhưng không tự kết luận vì sao `Customer` đang giữ địa chỉ null: do repository không tìm thấy bản ghi, mapper bỏ sót trường, constructor nhận null, cache hết hạn, hay một điều kiện khác.

**Sau bài này**, người học có thể:
- Phân biệt **nơi `null` xuất hiện**, **nơi lưu/truyền `null`**, và **nơi NPE xảy ra**.
- Đọc đúng hai vế của helpful NPE: thao tác thất bại và tham chiếu null ngay lúc thất bại.
- Nhận biết những trường hợp JVM không sinh mô tả hữu ích hoặc mô tả bị hạn chế.
- Truy vết nguyên nhân thực sự bằng stack trace, debugger, hợp đồng API, validation, log an toàn và kiểm thử.
- Áp dụng cách ngăn `null` đi xa qua boundary, mà không ỷ lại vào thông báo lỗi.

**Tính hiện hành:** JEP 358 ra mắt Java 14; tính năng vẫn có trong các JDK hiện đại. Ở **Java 14**, `-XX:+ShowCodeDetailsInExceptionMessages` **chưa bật mặc định**. Từ **Java 15**, cấu hình HotSpot mặc định bật; với Java 17+ thông thường không cần thêm flag. Dưới đây dùng `javac --release 17` và `java`/`java -XX:+ShowCodeDetailsInExceptionMessages`.

## 2. Ba vị trí khác nhau trong quá trình hình thành lỗi

Xét một luồng dữ liệu:

```text
readDatabase("C1") trả về null
             │
             ▼
Customer được tạo với component address = null
             │
             ▼
customer.address() trả về null
             │
             ▼
customer.address().city()  ← cố gọi method trên null
             │
             ▼
NullPointerException tại dòng gọi city()
```

Ở đây có ba khái niệm:

| Khái niệm | Ví dụ | Helpful NPE có tự cung cấp? |
| --- | --- | --- |
| **Nguồn xuất hiện `null` (origin)** | `readDatabase` không tìm thấy địa chỉ và trả `null` | **Không bảo đảm**; thường phải kiểm tra logic của `readDatabase` hoặc nguồn dữ liệu |
| **Vị trí mang/truyền `null` (propagation)** | Constructor `Customer("C1", null)` lưu giá trị; accessor `address()` trả lại | Có thể chỉ ra **lời gọi trả về `null` gần nhất**, nhưng không phải lịch sử đầy đủ |
| **Nơi sử dụng sai (*dereference*)** | `customer.address().city()` | **Có**, khi JVM tạo helpful NPE và đủ thông tin nội bộ |

Đây không phải ba thuật ngữ được JVM báo thành ba trường. Đó là cách tư duy để chẩn đoán chính xác: **JEP 358 chủ yếu quan sát thao tác thất bại và dựng lại biểu thức trên operand stack của bytecode hiện tại**; nó không thực hiện *whole-program data-flow tracing* xuyên qua mọi method, thread, database hoặc request.

### Một thông báo có chứa tên method vẫn chưa xác định gốc

```text
Cannot invoke "Address.city()" because
the return value of "Customer.address()" is null
```

Điều này chỉ cho biết **kết quả của lời gọi `Customer.address()` là `null` ở thời điểm gọi `city()`**. Chưa thể kết luận `Customer.address()` tạo ra `null`, hay nó chỉ trả lại field đã được lưu từ lâu; cũng chưa xác định method nguồn nào đã đưa `null` vào field.

## 3. JVM tính thông báo như thế nào?

Trong cách triển khai Helpful NPE của HotSpot, khi JVM tạo một `NullPointerException` do thao tác không hợp lệ trên `null`, phần thông báo chi tiết được dựng từ bytecode của phương thức tại vị trí lỗi. Nó có hai phần chính:

1. **Thao tác không thực hiện được**, chẳng hạn `Cannot invoke "...city()"`, `Cannot read field "..."`, `Cannot load from ... array`.
2. **Biểu thức đang `null` ngay lúc đó**, chẳng hạn `because "profile.email" is null` hoặc `because the return value of "...address()" is null`.

Ví dụ:

```java
class Profile {
    String email; // Nếu không được gán, field tham chiếu mặc định là null.
}

// Trích đoạn trong một method:
Profile profile = new Profile();
profile.email.length(); // NPE: lỗi ở chỗ gọi length().
```

Thông báo JVM hiện đại với thông tin biên dịch phù hợp:

```text
Cannot invoke "String.length()" because "profile.email" is null
```

Thông báo nói **field email đang null** và **`String.length()` không gọi được**. Từ riêng thông báo này, bạn chưa biết field đó chưa từng được khởi tạo, bị set null sau khi tạo object, hay được gán từ dữ liệu thiếu. Trong ví dụ hiện tại, vì đọc source nên biết trường chưa được khởi tạo; **đó là suy luận từ mã**, không phải điều JVM xác định từ lịch sử dữ liệu.

### Stack trace cũng không phải lịch sử mọi phép gán

Stack trace thường chứa method, file và dòng nơi exception được ném, cùng các lời gọi đang hoạt động trên call stack. Nó **không phải bản ghi đầy đủ các bước đã gán giá trị cho đối tượng**. Nếu một method trả null rồi kết thúc trước khi lời gọi hiện tại ném NPE, frame method đó có thể đã không còn trên stack.

Do đó:
- **Top stack frame** thường là điểm nên mở source để bắt đầu.
- **Helpful message** giúp chọn đúng biểu thức bị null ở điểm đó.
- **Root cause** yêu cầu truy ngược cách biểu thức ấy được cung cấp, qua constructor, field, method return, mapper, dữ liệu, nhánh điều khiển hoặc tương tác đa luồng.

## 4. Minh họa trọng tâm: hai nguồn `null` khác nhau, một thông báo giống hệt nhau

Đây là ví dụ rõ nhất cho giới hạn của JEP 358:

```java
record Address(String city) {}

static Address readCache(String id) {
    return null; // Mô phỏng cache không có dữ liệu.
}

static Address readDatabase(String id) {
    return null; // Mô phỏng database không tìm thấy bản ghi.
}

static void sameFailureSite(boolean useCache) {
    Address chosen = useCache ? readCache("C1") : readDatabase("C1");
    chosen.city(); // Cùng một điểm dereference.
}
```

Đây là **trích đoạn cần đặt trong class**; chương trình độc lập ở mục 9 chứa đầy đủ các khai báo tương ứng.

Khi gọi `sameFailureSite(true)`, `null` xuất phát từ `readCache`; khi gọi `sameFailureSite(false)`, nó xuất phát từ `readDatabase`. Nhưng cả hai lần NPE xảy ra ở **cùng dòng**:

```java
chosen.city();
```

Với JDK và debug metadata dùng trong ví dụ, **hai lần đều cho cùng thông báo**:

```text
Cannot invoke "NullOriginDemo$Address.city()" because "chosen" is null
```

Không có chữ `readCache` hay `readDatabase` trong thông báo; JVM không tự chọn “nguồn gốc” theo luồng dữ liệu lịch sử. Nó chỉ thấy tại lệnh gọi `city()`, biến `chosen` đang mang tham chiếu null.

**Hệ quả khi điều tra sự cố:** ngay cả khi thông báo đã chỉ đúng biến null, hãy hỏi tiếp: *“Giá trị của biến này đến từ đâu, và vì sao nhánh này lại cho phép null?”* Nếu chỉ chữa `chosen.city()` bằng kiểm tra null mà bỏ qua việc hiểu dữ liệu nguồn, có thể che giấu lỗi nghiệp vụ.

## 5. Lời gọi trả về `null` trong chuỗi method

Một chuỗi gọi method có thể giúp JVM mô tả **mắt xích gần nhất**:

```java
record Address(String city) {}
record Customer(String id, Address address) {}

// Trích đoạn:
Customer customer =
        new Customer("C1", readDatabase("C1"));

customer.address().city(); // address() trả null, sau đó gọi city().
```

Khi dùng code mẫu hoàn chỉnh, thông báo:

```text
Cannot invoke "NullOriginDemo$Address.city()" because the return value of "NullOriginDemo$Customer.address()" is null
```

Với `record Customer`, `address()` là **accessor** trả lại component field. JVM có thể chỉ ra giá trị trả về của accessor là null, nhưng không tự nói rằng `readDatabase("C1")` đã trả null và được đưa vào constructor trước đó.

Ngay cả khi một thông báo nêu tên method gọi ngay trước thao tác lỗi, không nên đánh đồng:

- **Method có kết quả đang null:** `Customer.address()`.
- **Method gây ra/đưa null vào dữ liệu trong ví dụ:** `readDatabase("C1")`.
- **Vị trí NPE:** lời gọi `city()` trên kết quả `address()`.

Để phát hiện sớm hơn, có thể đặt invariant trong constructor hoặc tại boundary nhận kết quả:

```java
record Customer(String id, Address address) {
    Customer {
        java.util.Objects.requireNonNull(id, "id");
        java.util.Objects.requireNonNull(address, "address");
    }
}
```

Constructor này **không cho một `Customer` hợp lệ được tạo ra với `address == null`**. Nó không tự giải thích lý do database thiếu địa chỉ, nhưng đưa điểm phát hiện về gần nơi vi phạm hợp đồng dữ liệu hơn.

Nếu **thiếu địa chỉ là trường hợp hợp lệ**, đừng ép `requireNonNull` một cách máy móc: hãy biểu diễn *absence* có chủ ý (ví dụ qua kết quả `Optional` của repository hoặc một trạng thái nghiệp vụ rõ ràng).

## 6. Nguồn `null` phổ biến mà helpful NPE không truy nguyên tự động

| Nguồn thực tế | Khi nào `null` xuất hiện? | NPE có thể xuất hiện ở đâu? | Nơi cần điều tra |
| --- | --- | --- | --- |
| Kết quả không tìm thấy | Repository/cache/API trả null | Khi gọi method trên kết quả | Hợp đồng repository, ID, query, cache miss |
| Field chưa khởi tạo | Field tham chiếu mặc định null | Khi đọc field rồi gọi method | Constructor, dependency injection, vòng đời object |
| Mapper thiếu dữ liệu | DTO/JSON/database thiếu property | Sau khi mapping hoặc tại service xử lý | Validation đầu vào, schema, version và mapping |
| Nhánh điều kiện bỏ sót gán | Đường chạy không có kết quả mong muốn | Sau khi thoát khỏi nhánh | Control flow, default/fallback |
| Collection chứa null | `List`/`Map` lưu phần tử hoặc value null tùy implementation | `forEach`/`map`/`get` trả null rồi gọi method | Dữ liệu ban đầu, policy của collection, kiểm tra phần tử |
| Đồng thời nhiều thread | Field dùng chung thay đổi qua các thời điểm | Tại bước đọc trong thread khác | Thiết kế đồng bộ, tính nhất quán, log sự kiện |
| Phép unboxing | `Integer` đang null bị chuyển sang `int` | Tại lời gọi `intValue()` ngầm định | Hợp đồng giá trị số, chỗ gán `Integer` |
| Tích hợp thư viện | Thư viện trả null theo hợp đồng hoặc thiếu config | Khi code khách hàng gọi tiếp | Tài liệu API, input, phiên bản, cách xử lý nullability |

Bảng không nói mọi trường hợp này chắc chắn ném NPE: **mang `null` là hợp lệ trong nhiều ngữ cảnh Java**. NPE chỉ xuất hiện khi có thao tác yêu cầu object thực, hoặc code chủ động ném `NullPointerException`.

### Trường hợp unboxing cần nhận biết

```java
Integer count = null;
// int value = count; // Nếu chạy: NPE do autounboxing gọi intValue().
```

Helpful NPE có thể nhắc đến `Integer.intValue()` thay vì câu lệnh chuyển sang `int` trong source. Đó là vì compiler triển khai unboxing bằng lời gọi method, **không phải JVM đã tìm ra nơi `count` được gán null**.

## 7. Khi nào thông báo không chi tiết hoặc không có thông báo?

### 7.1. NPE do code tự ném

```java
throw new NullPointerException("manual validation");
```

Chuỗi `"manual validation"` là **message do lập trình viên cung cấp**, không phải JEP 358 dựng lại từ thao tác dereference. Cũng vậy:

```java
throw new NullPointerException();
```

Thông thường `getMessage()` của NPE được tạo thủ công **không có mô tả helpful**. Không nên kết luận JVM hỏng chỉ vì một NPE không có vế `because ... is null`.

### 7.2. `Objects.requireNonNull` có message do ứng dụng quyết định

```java
Address address = java.util.Objects.requireNonNull(
        readCache("C1"), "address from cache");
```

Nếu giá trị null, `Objects.requireNonNull` ném NPE với thông báo `"address from cache"`. Đây là cách **phát hiện sớm có chủ đích**, cho biết **hợp đồng nào bị vi phạm**, nhưng vẫn không thể biết được vì sao cache miss nếu không theo dõi hoạt động của cache.

Một quy tắc tốt: message nên cung cấp **ngữ cảnh kỹ thuật có ích nhưng không chứa bí mật** (ví dụ tên thuộc tính/điều kiện), thay vì in toàn bộ thông tin nhạy cảm hoặc dữ liệu người dùng.

### 7.3. Bật/tắt tính năng trên Java hỗ trợ

| Môi trường | Tình trạng thường gặp |
| --- | --- |
| Java 14 HotSpot | JEP 358 được giới thiệu, **mặc định tắt**; dùng `-XX:+ShowCodeDetailsInExceptionMessages` |
| Java 15+ HotSpot | **Mặc định bật**; có thể tắt bằng `-XX:-ShowCodeDetailsInExceptionMessages` |
| Java 17+ | Tính năng đã ổn định, vẫn tuân theo cấu hình JVM và thông tin khả dụng |
| NPE ném tường minh, thông tin nội bộ không khả dụng | Không nhất thiết có thông báo helpful |
| NPE sau khi deserialize | API JDK nêu rằng thông tin nội bộ để dựng message helpful **không còn** |

Lệnh chạy thực tế:

```bash
java -XX:+ShowCodeDetailsInExceptionMessages -cp . NullOriginDemo
java -XX:-ShowCodeDetailsInExceptionMessages -cp . NullOriginDemo
```

**Lưu ý:** tên method, field, định dạng câu chữ của message là chi tiết chẩn đoán của JVM; có thể khác theo JDK, compiler, debug symbols hoặc cách xây dựng bytecode. **Không parse helpful NPE text để quyết định logic nghiệp vụ**, không viết assertion cứng vào toàn bộ văn bản message nếu không kiểm soát phiên bản/runtime.

### 7.4. `-g` giúp tên biến, không giúp tìm nơi null sinh ra

Compiler có thể lưu tên biến local trong class file nếu dùng `javac -g` hoặc `-g:vars`. Khi tên local không có, VM có thể dùng định danh dạng `<local1>` hoặc `<parameter1>` thay tên người đọc hiểu được.

```bash
javac --release 17 -g NullOriginDemo.java
java -XX:+ShowCodeDetailsInExceptionMessages NullOriginDemo
```

Trong ví dụ đã kiểm chứng, tên `chosen` xuất hiện nhờ biên dịch với debug info. Nếu không có metadata, cách JVM mô tả biến có thể chung chung hơn. Nhưng **dù có đầy đủ tên biến**, hệ thống vẫn không tự khôi phục lịch sử `readCache` so với `readDatabase` của biến `chosen`.

Thông tin line/file trong stack trace cũng phụ thuộc debug metadata. Điều này không thay đổi ý nghĩa: stack trace là đường gọi khi lỗi xảy ra, **không phải toàn bộ lịch sử sự kiện**.

## 8. Hướng dẫn đọc thông báo cho đúng

Mẫu thường gặp:

```text
java.lang.NullPointerException:
  Cannot invoke "X.method()" because "something" is null
```

Đọc theo thứ tự:

1. **`Cannot invoke "X.method()"`:** hành động JVM cố thực hiện và đã thất bại.
2. **`because "something" is null`:** biểu thức đang null ngay trước hành động.
3. **Frame đầu tiên trong stack trace thuộc code liên quan:** tìm file, method và dòng dereference.
4. **Kiểm tra nguồn của biểu thức:** field được khởi tạo ở đâu? method trả giá trị theo hợp đồng nào? request hoặc database trả dữ liệu gì?
5. **Tái hiện và kiểm tra giả thuyết:** biến nào thực sự bị null, điều kiện nào tạo ra giá trị này, invariant nào bị vi phạm?

Không nên diễn giải `"because the return value of getAddress() is null"` thành “getAddress() là bug”. `getAddress()` có thể hoạt động đúng hợp đồng trả lại field null; **bug thật sự** có thể là dữ liệu thiếu, điều kiện không được xử lý, hoặc caller không thực hiện null-check đúng quy ước.

### Bảng “biết gì” và “chưa biết gì”

| Helpful NPE cho bạn | Nó không bảo đảm cung cấp |
| --- | --- |
| Thao tác bị lỗi (invoke, read field, array access...) | Vì sao dữ liệu thiếu |
| Biểu thức/trung gian có giá trị null tại bytecode đang chạy | Method nào đã tạo ra hoặc lần đầu gán null |
| Vị trí NPE trong stack trace khi stack thông tin khả dụng | Mọi assignment/event trước khi exception |
| Tên field/method gần thao tác thất bại | Đường chạy của database, cache, message broker |
| Một dấu hiệu để bắt đầu debug nhanh hơn | Chẩn đoán nguyên nhân gốc hoàn chỉnh hoặc cách sửa tự động |

## 9. Chương trình độc lập Java 17+ đã biên dịch, chạy và đối chiếu đầu ra

Lưu thành **`NullOriginDemo.java`**:

```java
import java.util.Objects;

public class NullOriginDemo {
    record Address(String city) {}
    record Customer(String id, Address address) {}

    static Address readCache(String id) {
        return null; // Mô phỏng một nguồn không có dữ liệu.
    }

    static Address readDatabase(String id) {
        return null; // Mô phỏng một nguồn khác không có dữ liệu.
    }

    static void sameFailureSite(boolean useCache) {
        Address chosen = useCache ? readCache("C1") : readDatabase("C1");
        chosen.city(); // Một điểm NPE cho hai nguồn khác nhau.
    }

    static void chainedFailure() {
        Customer customer = new Customer("C1", readDatabase("C1"));
        customer.address().city();
    }

    static class Profile {
        String email;
    }

    static void defaultFieldFailure() {
        Profile profile = new Profile();
        profile.email.length();
    }

    static void validateEarly() {
        Address address = Objects.requireNonNull(
                readCache("C1"), "address from cache");
        System.out.println(address.city());
    }

    static void manualException() {
        throw new NullPointerException("manual validation");
    }

    static void report(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": no exception");
        } catch (NullPointerException ex) {
            System.out.println(label + ": " + ex.getMessage());
            System.out.println("atMethod="
                    + ex.getStackTrace()[0].getMethodName());
        }
    }

    public static void main(String[] args) {
        report("cache", () -> sameFailureSite(true));
        report("database", () -> sameFailureSite(false));
        report("chain", NullOriginDemo::chainedFailure);
        report("field", NullOriginDemo::defaultFieldFailure);
        report("boundary", NullOriginDemo::validateEarly);
        report("explicit", NullOriginDemo::manualException);
    }
}
```

Dùng JDK 17+ (ví dụ biên dịch với debug info để thấy tên `chosen`):

```bash
javac --release 17 -g NullOriginDemo.java
java -XX:+ShowCodeDetailsInExceptionMessages NullOriginDemo
```

**Stdout chính xác** trên HotSpot/JDK đã kiểm tra:

```text
cache: Cannot invoke "NullOriginDemo$Address.city()" because "chosen" is null
atMethod=sameFailureSite
database: Cannot invoke "NullOriginDemo$Address.city()" because "chosen" is null
atMethod=sameFailureSite
chain: Cannot invoke "NullOriginDemo$Address.city()" because the return value of "NullOriginDemo$Customer.address()" is null
atMethod=chainedFailure
field: Cannot invoke "String.length()" because "profile.email" is null
atMethod=defaultFieldFailure
boundary: address from cache
atMethod=requireNonNull
explicit: manual validation
atMethod=manualException
```

### Giải thích stdout

- **`cache` và `database`** khác nhánh nguồn nhưng **cùng message và cùng method dereference `sameFailureSite`**. Đây là bằng chứng trực tiếp rằng helpful NPE **không truy ra nơi sinh `null`**.
- **`chain`** cho biết `Customer.address()` trả null, không cho biết `readDatabase` đã trả null trước đó.
- **`field`** chỉ ra `profile.email` đang null, nhưng chính bạn phải xem `Profile` để nhận ra nó chưa được khởi tạo.
- **`boundary`** được tạo bởi `Objects.requireNonNull` với message rõ ràng; top method là `requireNonNull`, không phải nguyên nhân sâu của cache miss.
- **`explicit`** là NPE do lập trình viên ném và mang message tự khai báo.

### Tắt helpful messages để quan sát sự khác biệt

```bash
java -XX:-ShowCodeDetailsInExceptionMessages NullOriginDemo
```

Kết quả khi tắt flag, cùng bản class đã biên dịch:

```text
cache: null
atMethod=sameFailureSite
database: null
atMethod=sameFailureSite
chain: null
atMethod=chainedFailure
field: null
atMethod=defaultFieldFailure
boundary: address from cache
atMethod=requireNonNull
explicit: manual validation
atMethod=manualException
```

Khi flag tắt, các NPE do VM tạo trong `sameFailureSite`, `chainedFailure` và `defaultFieldFailure` không còn thông báo mô tả. Nhưng thông báo **được lập trình viên truyền vào** qua `Objects.requireNonNull` và `new NullPointerException(String)` không biến mất vì chúng **không phải thông báo do JEP 358 tổng hợp**.

**Lưu ý khi thực hành:** stdout cụ thể ở trên được xác minh với phiên bản/runtime đã dùng. Với các JDK/JVM khác, chi tiết nội bộ của message có thể khác; **hai trường hợp cùng điểm dereference** vẫn minh họa giới hạn không có lịch sử gán biến.

## 10. Quy trình tìm nguồn `null` thật sự trong một bug

Ví dụ nhận lỗi `chosen.city()`:

### Bước 1 — Xác định *dereference site*

Đọc thao tác lỗi `Cannot invoke "...city()"` và biểu thức null `chosen`. Mở frame đầu tiên của stack trace thuộc mã ứng dụng; xem source quanh điểm ném. Phân biệt chỗ **ném NPE** với chỗ **đã đưa null vào dữ liệu**.

### Bước 2 — Truy theo định nghĩa và assignment của biểu thức

Trong ví dụ, `chosen` có thể nhận kết quả của `readCache` hoặc `readDatabase`. Kiểm tra nhánh `useCache` ngay lần chạy lỗi, điều kiện đầu vào, tên ID, và hợp đồng hai hàm.

Đối với một field, kiểm tra constructor, setter (nếu có), dependency injection, mapper, trạng thái mặc định và các đường cập nhật. Đối với giá trị trả từ method, mở implementation và xem các `return null`, `map.get`, `find`, `catch` fallback hoặc branches.

### Bước 3 — Dùng debugger để dừng ở **nơi giá trị được sinh**

Đặt breakpoint trước assignment hoặc ngay trong method nguồn, quan sát kết quả trả về và nhánh thực tế. Nếu bug không ổn định, có thể dùng conditional breakpoint cho ID/request liên quan hoặc tracing ở boundary (trong giới hạn hiệu năng và bảo mật).

Ví dụ đặt breakpoint trong `readCache("C1")`/`readDatabase("C1")` sẽ nhanh chóng cho thấy đường nguồn nào được chạy; breakpoint chỉ tại `chosen.city()` giúp thấy `null` nhưng **không tự kể lại quá khứ**.

### Bước 4 — Ghi log có ngữ cảnh nhưng bảo vệ dữ liệu

Ở nơi lấy dữ liệu, ghi trạng thái `found/missing` hoặc lý do nghiệp vụ, request correlation ID và tên nguồn, thay vì chỉ log NPE muộn. Tránh ghi token, mật khẩu, thông tin cá nhân hoặc toàn bộ payload vào exception/log. Không trả stack trace và message nội bộ cho client không đáng tin; message có thể lộ tên class/field/method và gợi ý cấu trúc ứng dụng.

### Bước 5 — Quy định hợp đồng nullability rõ ràng

Chọn một trong các hướng:
- Nếu giá trị **bắt buộc tồn tại**, kiểm tra ở boundary bằng `Objects.requireNonNull(value, "address")` hoặc validate có ngữ cảnh, rồi xử lý lỗi thích hợp ở tầng nghiệp vụ.
- Nếu giá trị **có thể vắng mặt hợp lệ**, thiết kế API biểu đạt sự vắng mặt, ví dụ `Optional<Address> findAddress(String id)`; caller xử lý `empty` thay vì gọi method trên null.
- Nếu là giá trị **mặc định hợp lệ**, cung cấp fallback có chủ ý, kiểm tra tác động nghiệp vụ và không mặc định nuốt lỗi.

Ví dụ dùng `Optional` (đoạn minh họa, không phải thay thế tùy tiện cho mọi kiểu trường):

```java
static java.util.Optional<Address> findAddress(String id) {
    return java.util.Optional.ofNullable(readDatabase(id));
}

static String cityOrUnknown(String id) {
    return findAddress(id)
            .map(Address::city)
            .orElse("UNKNOWN");
}
```

Đoạn trên xử lý case không có địa chỉ như một khả năng nghiệp vụ. Với hệ thống không cho phép thiếu địa chỉ, nên **fail fast** thay vì âm thầm dùng `"UNKNOWN"` làm dữ liệu giả. Nếu `Address.city()` cũng trả null, cần định nghĩa hợp đồng đối với component `city`.

### Bước 6 — Viết test tái hiện cả nguồn và điểm dùng

Thử các trường hợp: cache hit/miss, repository có/không bản ghi, địa chỉ null trong constructor, field chưa khởi tạo, chuỗi method và các nhánh fallback. Kiểm tra **hành vi và hợp đồng**, không buộc assertion phải khớp nguyên văn message helpful NPE theo từng JDK.

Mục tiêu cuối là sửa **đường tạo/truyền dữ liệu không phù hợp** hoặc **xử lý thiếu vắng đúng quy định**, không chỉ thêm một null-check ở cuối để ngăn NPE rồi bỏ qua nguyên nhân.

## 11. Các ngộ nhận cần tránh

### Ngộ nhận A — Message có tên biến tức là JVM đã biết nơi biến được gán null

Sai. Tên `chosen` có thể chỉ nhờ debug information, còn các phép gán trước đó không được “ghi lịch sử” để truy vết tự động. Hai nhánh cache/database trong demo chứng minh hai nguồn tạo cùng message.

### Ngộ nhận B — Message nêu return value thì method ấy nhất định có bug

Chưa đủ căn cứ. `Customer.address()` có thể đơn giản trả lại field và hoạt động đúng hợp đồng. Việc constructor nhận `null` hoặc data source trả `null` có thể mới là chỗ cần sửa.

### Ngộ nhận C — Stack trace là đầy đủ call history dẫn đến null

Không. Stack trace cho biết stack tại thời điểm exception, không phải nhật ký mọi lời gọi đã hoàn tất và mọi gán field/biến. Một method đã trả null trước đó có thể không còn trên stack.

### Ngộ nhận D — JEP 358 tự làm ứng dụng an toàn với null

Không. `NullPointerException` vẫn xảy ra khi dùng null sai. JEP chỉ cải thiện khả năng **chẩn đoán**, không thêm kiểu non-null, tự điền dữ liệu thiếu, tự kiểm tra constructor hay ngăn race condition.

### Ngộ nhận E — Bật flag sẽ làm mọi `NullPointerException` có message chi tiết

Không. NPE do code tự tạo/throw, NPE thiếu thông tin nội bộ hoặc NPE đã deserialize không nhất thiết có mô tả helpful. Flag chỉ tác động vào khả năng JVM tạo message chẩn đoán khi điều kiện hỗ trợ phù hợp.

### Ngộ nhận F — Dùng `Optional` ở mọi nơi là cách sửa duy nhất

Không. `Optional` phù hợp nhất ở API biểu đạt **giá trị có thể vắng mặt**, đặc biệt return type. Không cần bọc tất cả field, tham số và collection element thành `Optional`. Với giá trị bắt buộc, validation và invariant rõ ràng thường tốt hơn; với trạng thái nghiệp vụ phức tạp, kiểu kết quả riêng cũng có thể phù hợp.

### Ngộ nhận G — Đọc message rồi gửi thẳng cho người dùng cuối là vô hại

Không. Helpful NPE có thể chứa tên component, class, field và cách gọi nội bộ. Nên log/tracing có quyền truy cập thích hợp, còn giao diện/public API trả thông tin lỗi an toàn, đủ cho người dùng nhưng không tiết lộ chi tiết triển khai.

## 12. Bài tập tự kiểm tra

**Câu 1:** `Cannot invoke "String.length()" because "profile.email" is null` chứng minh điều gì?

**Đáp án:** JVM xác định hành động gọi `length()` không thực hiện được vì biểu thức `profile.email` đang null ở điểm ném NPE. Nó **không tự chứng minh** email chưa bao giờ được gán, được gán null ở đâu hoặc vì sao thiếu dữ liệu.

**Câu 2:** Hai lệnh `Address chosen = readCache(id); chosen.city();` và `Address chosen = readDatabase(id); chosen.city();` có thể sinh cùng helpful NPE không?

**Đáp án:** Có. Nếu mỗi nguồn trả null và cùng method/bytecode dereference, JVM có thể báo cùng `"chosen" is null`. Truy nguồn phải theo nhánh xử lý và hợp đồng của cache/database.

**Câu 3:** `the return value of "Customer.address()" is null` có khẳng định database tạo null không?

**Đáp án:** Không. Nó chỉ khẳng định accessor trả null ở chỗ dùng; cần xem constructor và dữ liệu nguồn để tìm nơi `null` đi vào `Customer`.

**Câu 4:** Vì sao `Objects.requireNonNull(address, "address")` có ích dù không đưa ra nguyên nhân sâu?

**Đáp án:** Nó thất bại **sớm tại ranh giới hợp đồng**, cung cấp thông báo do code định nghĩa. Điều này thu hẹp phạm vi tìm bug, nhưng bản thân nó không truy được vì sao upstream trả null.

**Câu 5:** `-g` có làm JVM biết method nào đầu tiên sinh `null` không?

**Đáp án:** Không. `-g` lưu thêm debug metadata như tên biến local và dòng source; nó có thể giúp message dễ đọc, không tạo lịch sử data provenance.

**Câu 6:** Từ Java 15+, HotSpot có cần bật JEP 358 bằng flag để nhìn thấy helpful NPE không?

**Đáp án:** Thông thường **không**: `ShowCodeDetailsInExceptionMessages` đã bật mặc định. Có thể dùng dấu `+` để bật rõ ràng hoặc `-` để tắt khi cần chẩn đoán/so sánh.

**Câu 7:** Vì sao NPE sau deserialize có thể không còn message helpful?

**Đáp án:** `NullPointerException.getMessage()` của JDK ghi rõ mô tả mở rộng chỉ có khi thông tin nội bộ còn khả dụng; thông tin này không còn ở NPE đã deserialize.

**Câu 8:** Nếu `findAddress` được phép không tìm thấy dữ liệu, nên chữa `findAddress(id).city()` ra sao?

**Đáp án:** Thiết kế kết quả có thể vắng mặt (`Optional`/kiểu trạng thái) và xử lý absent theo nghiệp vụ, hoặc kiểm tra null với thông báo rõ. Không tự sử dụng dữ liệu giả khi không phù hợp hợp đồng.

## 13. Checklist xử lý bug NPE trong dự án

- [ ] Xác định **chỗ dereference** từ helpful message và top frame; không tự coi đó là **nguồn tạo null**.
- [ ] Tách ba câu hỏi: `null` đến từ đâu, được lưu/truyền qua đâu, và bị dùng sai ở đâu?
- [ ] Đối chiếu trạng thái dữ liệu ở boundary (repository/cache/API/mapper/constructor), bao gồm các nhánh đặc biệt.
- [ ] Dùng debugger/conditional breakpoint hoặc log có correlation ID để truy nguồn; không log bí mật.
- [ ] Bật debug info như `javac -g` khi hữu ích, nhưng không kỳ vọng metadata tạo data provenance.
- [ ] Phân biệt NPE do JVM tạo với NPE tự ném và `Objects.requireNonNull`.
- [ ] Nhớ flag Java 14 mặc định tắt, Java 15+ HotSpot mặc định bật; kiểm tra cấu hình JVM thực tế.
- [ ] Không parse hoặc phụ thuộc nguyên văn message JVM trong nghiệp vụ/tests xuyên phiên bản.
- [ ] Với dữ liệu bắt buộc, kiểm tra sớm tại boundary; với dữ liệu vắng mặt hợp lệ, biểu đạt sự vắng mặt rõ ràng.
- [ ] Kiểm thử các case null từ nhiều nguồn chứ không chỉ case nơi NPE được ném.
- [ ] Không đưa stack trace hoặc thông báo nội bộ ra public response; kiểm soát thông tin nhạy cảm.

## Tài liệu chính thức còn áp dụng

1. [OpenJDK — JEP 358: Helpful NullPointerExceptions](https://openjdk.org/jeps/358): mục tiêu chẩn đoán thông qua bytecode tại chỗ JVM ném NPE, không cung cấp lịch sử nguồn dữ liệu đầy đủ.
2. [Oracle — The `java` Command, Java SE 17, `ShowCodeDetailsInExceptionMessages`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): flag bật/tắt và cách JVM suy ra tham chiếu null từ bytecode; bật mặc định trên Java 17.
3. [Oracle — The `java` Command, Java SE 14](https://docs.oracle.com/en/java/javase/14/docs/specs/man/java.html): cùng flag nhưng **mặc định tắt** trong Java 14.
4. [Oracle — JDK 15 Release Notes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): thay đổi mặc định của `ShowCodeDetailsInExceptionMessages` sang `true` từ JDK 15.
5. [Oracle — NullPointerException API, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NullPointerException.html): `getMessage()` có thể cung cấp mô tả khi có thông tin nội bộ; NPE được deserialize không có thông tin đó.
6. [Oracle — Objects API, Java SE 17, `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): xác thực giá trị bắt buộc tại boundary và thông báo có chủ đích.
