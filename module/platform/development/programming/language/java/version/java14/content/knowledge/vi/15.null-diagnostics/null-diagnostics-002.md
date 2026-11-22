# Xác định phép truy cập thất bại trong chuỗi biểu thức — Helpful NullPointerExceptions (Java 14+)

> Mục tiêu: đọc thông báo `NullPointerException` để xác định **phép truy cập nào bị chặn** và **biểu thức con nào trả về `null`** trong một chuỗi gọi nhiều cấp. Tính năng *Helpful NullPointerExceptions* (JEP 358) xuất hiện từ Java 14 và tiếp tục dùng trong Java hiện đại; bài tập dùng **JDK 17+**, không yêu cầu tính năng preview hay kỹ thuật legacy.

## 1. Vì sao chuỗi gọi nhiều cấp khó chẩn đoán?

Xét một biểu thức truy cập các lớp dữ liệu lồng nhau:

```java
String result = order.customer().address().city().toUpperCase();
```

Trình biên dịch tạo những bước tương ứng: đọc tham chiếu `order`, gọi `customer()` trên nó, gọi `address()` trên kết quả, gọi `city()` trên kết quả tiếp theo, rồi gọi `toUpperCase()` trên chuỗi vừa nhận. Mỗi lời gọi instance method đều **cần receiver khác `null`**.

Khi một mắt xích trả `null`, chương trình chưa chắc lỗi ngay tại mắt xích ấy. Lỗi thường phát sinh **ở phép truy cập kế tiếp**, khi JVM cố dùng giá trị `null` làm receiver. Trước khi có thông điệp chi tiết, chỉ biết NPE ở một dòng như trên thường chưa đủ để xác định đoạn nào bị lỗi.

Helpful NPE giúp JVM phân tích bytecode của phép truy cập thất bại và mô tả phần tham chiếu liên quan. **Nó chỉ ra nơi lỗi được kích hoạt, không tự giải thích nguyên nhân nghiệp vụ tạo ra dữ liệu null.**

## 2. Phạm vi Java hiện hành

- **Java 14:** JEP 358 giới thiệu cơ chế chẩn đoán NPE chi tiết cho những ngoại lệ do JVM tạo khi sử dụng tham chiếu `null`. Ở bản Java 14, việc bật tùy chọn có thể cần khai báo rõ.
- **Java 15+ và JDK 17+ HotSpot:** `ShowCodeDetailsInExceptionMessages` được bật theo mặc định. Thông thường không cần sửa mã nguồn hoặc cài thư viện.
- Có thể bật rõ ràng bằng `java -XX:+ShowCodeDetailsInExceptionMessages ...` và tắt trong môi trường thử nghiệm bằng `java -XX:-ShowCodeDetailsInExceptionMessages ...`.
- Đây là hỗ trợ chẩn đoán, **không** làm thay đổi thời điểm chương trình ném NPE, loại ngoại lệ hoặc quy tắc hoạt động của Java.
- Theo API chính thức, `NullPointerException.getMessage()` vẫn **có thể trả `null`** khi thông tin chi tiết không có sẵn; không coi helpful message là giao diện dữ liệu có định dạng cố định.

`-XX` là tham số khi **chạy JVM**, không phải lệnh Java viết trong thân class. Với mã trong bài, có thể kiểm tra JDK đang sử dụng bằng `java -version`.

## 3. Đọc một thông báo Helpful NPE như thế nào?

Thông báo điển hình trên HotSpot:

```text
Cannot invoke "HelpfulNpeChainDemo$Address.city()" because the return value of "HelpfulNpeChainDemo$Customer.address()" is null
```

Chia làm hai vế:

1. **`Cannot invoke "…Address.city()"`**: JVM muốn gọi phương thức instance `city()` nhưng không thực hiện được.
2. **`because the return value of "…Customer.address()" is null`**: kết quả của lời gọi `Customer.address()` chính là tham chiếu null được đặt làm receiver cho `city()`.

Suy ra: trong lần chạy đó, chương trình đã đi qua phép gọi `customer()` và thực thi `address()`. Lời gọi `address()` hoàn thành bình thường nhưng **trả `null`**; bước kế tiếp `city()` không bắt đầu được.

Không suy diễn rằng `city()` đã chạy và trả `null`: nếu `city()` trả null, phép `toUpperCase()` ở ngay sau nó mới là chỗ bị chặn, và message sẽ chỉ tới **`String.toUpperCase()`**.

### Một chuỗi, nhiều trường hợp null khác nhau

| Biểu thức con null | Thao tác không thực hiện được | Dấu hiệu thông điệp |
|---|---|---|
| Chính `order` | `order.customer()` | `Cannot invoke ...Order.customer()`, nguyên nhân `order` null (nếu biết tên) |
| Kết quả `order.customer()` | `.address()` | `return value of "...Order.customer()" is null` |
| Kết quả `customer.address()` | `.city()` | `return value of "...Customer.address()" is null` |
| Kết quả `address.city()` | `.toUpperCase()` | `return value of "...Address.city()" is null` |

Phần **`Cannot ...`** cho biết thao tác bị ngăn, phần **`because ... is null`** chỉ ra giá trị gây ra việc ngăn ấy. Tên lớp lồng nhau đôi khi được in dạng JVM `Outer$Nested` thay cho cú pháp nguồn `Outer.Nested`.

## 4. NPE có thể phát sinh ở những kiểu truy cập nào?

JVM có thể hỗ trợ mô tả các dạng truy cập null sau, không chỉ chuỗi gọi method:

| Loại phép truy cập | Ví dụ | Dạng thông điệp tiêu biểu |
|---|---|---|
| Gọi instance method | `node.next()` khi `node` null | `Cannot invoke ... because ... is null` |
| Đọc field | `node.value` khi `node` null | `Cannot read field "value" because ... is null` |
| Gán field | `node.value = 5` khi `node` null | `Cannot assign field "value" because ... is null` |
| Lấy `length` của mảng | `items.length` khi `items` null | `Cannot read the array length ...` |
| Đọc phần tử của mảng null | `items[0]` khi `items` null | `Cannot load from ... array ...` |
| Ghi phần tử vào mảng null | `items[0] = x` khi `items` null | `Cannot store to ... array ...` |
| Gọi method trên phần tử null | `names[0].length()` khi `names[0]` null | `Cannot invoke "String.length()" because "names[0]" is null` |
| Tự động unbox wrapper null | `int n = map.get("sold");` | Có thể xuất hiện `Cannot invoke "java.lang.Integer.intValue()"` |

Tên field, tên method, tên loại array và cách hiển thị có thể khác theo bytecode/JVM. Bảng minh họa **hình dạng thông báo**, không phải khuôn mẫu bắt buộc để chương trình parse.

**Phân biệt lỗi khác:** truy cập `items[10]` trên mảng không-null nhưng index vượt phạm vi gây `ArrayIndexOutOfBoundsException`, không phải NPE. Ép kiểu sai có thể gây `ClassCastException`. Hãy xác định chính xác exception type từ stack trace trước khi điều tra.

### Auto-unboxing và `Map.get()`

```java
java.util.Map<String, Integer> counts = java.util.Map.of();
int sold = counts.get("sold");
```

`Map.get("sold")` trả `null` vì không có khóa tương ứng. Do biến đích là primitive `int`, trình biên dịch yêu cầu unbox bằng cách gọi `Integer.intValue()` trên kết quả. **Chính phép unboxing `null` tạo NPE**, không phải việc `Map.get()` trả `null`.

Vì thế có thể gặp message:

```text
Cannot invoke "java.lang.Integer.intValue()" because the return value of "java.util.Map.get(Object)" is null
```

Trong các lỗi kiểu này, cần xét cả **phép chuyển kiểu ngầm** mà bytecode có thể thêm vào dù source không viết `intValue()` trực tiếp.

## 5. Chương trình Java đầy đủ đã kiểm tra với JDK 24

Tạo tệp **`HelpfulNpeChainDemo.java`** sau. Mã tương thích JDK 17+: các `record` trong ví dụ là cú pháp Java chính thức từ Java 16, chỉ để tạo mô hình dữ liệu ngắn gọn; cơ chế Helpful NPE vẫn là tính năng Java 14+.

```java
import java.util.Map;

public class HelpfulNpeChainDemo {
    record Address(String city) {}
    record Customer(Address address) {}
    record Order(Customer customer) {}

    static String upperCity(Order order) {
        return order.customer().address().city().toUpperCase();
    }

    static int firstNameLength(String[] names) {
        return names[0].length();
    }

    static int soldUnits(Map<String, Integer> counts) {
        return counts.get("sold");
    }

    static void show(String label, Runnable action) {
        try {
            action.run();
        } catch (NullPointerException ex) {
            System.out.println(label + " => " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        show("missing address", () ->
            System.out.println(upperCity(new Order(new Customer(null)))));
        show("missing customer", () ->
            System.out.println(upperCity(new Order(null))));
        show("missing city", () ->
            System.out.println(upperCity(new Order(new Customer(new Address(null))))));
        show("null array element", () ->
            System.out.println(firstNameLength(new String[] {null})));
        show("missing map value", () ->
            System.out.println(soldUnits(Map.of())));
        show("explicit exception", () -> {
            throw new NullPointerException("required field");
        });
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 -g HelpfulNpeChainDemo.java
java HelpfulNpeChainDemo
```

Tùy chọn `-g` giúp `javac` ghi thông tin debug gồm tên local variable vào `.class` để JVM có thể sử dụng khi dựng message. Không cần `--enable-preview`.

**Stdout chính xác được xác nhận với HotSpot OpenJDK 24, biên dịch `javac -g`:**

```text
missing address => Cannot invoke "HelpfulNpeChainDemo$Address.city()" because the return value of "HelpfulNpeChainDemo$Customer.address()" is null
missing customer => Cannot invoke "HelpfulNpeChainDemo$Customer.address()" because the return value of "HelpfulNpeChainDemo$Order.customer()" is null
missing city => Cannot invoke "String.toUpperCase()" because the return value of "HelpfulNpeChainDemo$Address.city()" is null
null array element => Cannot invoke "String.length()" because "names[0]" is null
missing map value => Cannot invoke "java.lang.Integer.intValue()" because the return value of "java.util.Map.get(Object)" is null
explicit exception => required field
```

Các thông điệp này mô tả đúng các lỗi của mã chạy trên JDK đã kiểm tra; **cách viết đầy đủ của method, loại, tên biến và phần chú thích có thể khác trên một JVM hoặc bản build khác**. Đừng kiểm thử nghiệp vụ bằng cách đòi toàn bộ message trùng chuỗi mẫu.

**Giải thích kết quả:**

- `missing address`: `Customer.address()` trả `null`; JVM không gọi được `Address.city()`.
- `missing customer`: `Order.customer()` trả `null`; JVM không gọi được `Customer.address()`.
- `missing city`: `Address.city()` trả `null`; phép gọi `String.toUpperCase()` kế tiếp lỗi.
- `null array element`: mảng tồn tại, nhưng `names[0]` null; thao tác lỗi là gọi `String.length()`.
- `missing map value`: giá trị được lấy từ `Map.get()` null, unboxing `Integer.intValue()` thất bại.
- `explicit exception`: lệnh `throw new NullPointerException("required field")` đã cung cấp message thủ công, không cần JVM tái tạo chuỗi truy cập.

`show` bắt NPE chỉ để minh họa nhiều tình huống trong một lần chạy. Trong ứng dụng thực, **không nên bắt mọi NPE rồi tiếp tục** nếu state không còn hợp lệ.

## 6. Quy trình lần ngược nguyên nhân null

Khi production log có NPE trong chuỗi biểu thức, xử lý theo trình tự:

1. **Xác nhận loại ngoại lệ.** Có đúng `NullPointerException` hay là `ClassCastException`, `ArrayIndexOutOfBoundsException`, lỗi xử lý JSON hoặc lỗi nghiệp vụ?
2. **Đọc thao tác thất bại.** Mệnh đề `Cannot invoke/read/assign/load/store` cho biết JVM đang cố làm gì.
3. **Tìm giá trị null.** Mệnh đề `because ... is null` cho biết receiver hoặc biểu thức con trả null. Với `return value of X()`, hãy truy ngược **X() đã trả kết quả gì**.
4. **Đọc stack trace.** Tìm phương thức/file/dòng đầu tiên liên quan tới mã ứng dụng. Một dòng có nhiều dấu chấm vẫn cần message chi tiết để phân biệt mắt xích.
5. **Theo luồng dữ liệu ngược về nơi tạo.** Kiểm tra mapper, repository, API response, constructor, các nhánh điều kiện và trạng thái mutable; tìm *vì sao* giá trị vắng mặt.
6. **Xác định hợp đồng dữ liệu.** Null được phép (phải có nhánh xử lý) hay bị cấm (phải kiểm tra và từ chối ở biên)?
7. **Viết test cho nguyên nhân thật.** Test tình huống đủ dữ liệu và từng trường thiếu cần thiết, không chỉ kiểm tra có một câu message tiếng Anh.

### Tách chuỗi dài để tìm nguyên nhân

Thay vì chỉ đọc một dòng:

```java
return order.customer().address().city().toUpperCase();
```

Có thể tách và kiểm tra rõ ràng (snippet trong một phương thức có biến `order` và các kiểu tương ứng):

```java
java.util.Objects.requireNonNull(order, "order is required");
Customer customer = java.util.Objects.requireNonNull(
    order.customer(), "customer is required");
Address address = java.util.Objects.requireNonNull(
    customer.address(), "address is required");
String city = java.util.Objects.requireNonNull(
    address.city(), "city is required");
return city.toUpperCase(java.util.Locale.ROOT);
```

`Objects.requireNonNull` ném ngoại lệ với **message do lập trình viên định nghĩa** khi vi phạm invariant. Đây là cách **kiểm tra hợp đồng tại nơi phù hợp**, không phải cách biến mọi nullable value thành non-null. Nếu thiếu địa chỉ là tình huống hợp lệ, phải thể hiện nhánh nghiệp vụ khác thay vì ném lỗi.

**Chú ý:** `java.util.Objects.requireNonNull(order.customer(), ...)` vẫn phải thực hiện `order.customer()` trước; do đó cần xác nhận bản thân `order` khác null khi cần. Một chuỗi kiểm tra sai thứ tự có thể gây NPE trước khi tới thông điệp do mình đặt.

## 7. Vì sao đôi khi message không chi tiết?

### 7.1. NPE được tạo thủ công không có truy cập bytecode cần suy luận

```java
throw new NullPointerException("customer is required");
```

Ngoại lệ trên chủ động truyền message. Helpful NPE dùng để mô tả trường hợp **JVM tạo NPE khi một phép truy cập cụ thể bị lỗi**, không tự thay message đã truyền trong constructor. Các helper như `Objects.requireNonNull(x, "...")` thường chủ động báo lỗi ở nơi kiểm tra.

Theo Javadoc, `getMessage()` có thể là `null` khi không có message tường minh và thông tin phân tích không còn khả dụng, kể cả một số trường hợp đối tượng NPE đã trải qua serialize/deserialize.

### 7.2. Thiếu tên biến cục bộ vì file `.class` không có debug metadata

Tên method và field thường có mặt trong thông tin bytecode. Tuy nhiên **tên local variable hoặc parameter** có thể bị compiler không ghi. Khi đó thông điệp có thể xuất hiện placeholder như `<local1>` hoặc `<parameter1>` thay vì tên nguồn thực tế.

```bash
javac -encoding UTF-8 -g HelpfulNpeChainDemo.java
```

Cờ `-g` có thể giúp cung cấp tên local variable và file/dòng cho chẩn đoán. Nó **không sửa dữ liệu null hoặc làm thay đổi ngữ nghĩa**. Nếu có thể, dùng cấu hình build debug của dự án trong môi trường phát triển/kiểm thử thay vì thay đổi tùy tiện cấu hình production.

### 7.3. Flag JVM bị tắt hoặc runtime không có đủ thông tin

```bash
java -XX:+ShowCodeDetailsInExceptionMessages HelpfulNpeChainDemo
java -XX:-ShowCodeDetailsInExceptionMessages HelpfulNpeChainDemo
```

Lệnh thứ nhất bật rõ chế độ chi tiết. Lệnh thứ hai tắt để đối chiếu: NPE do JVM tạo có thể chỉ có message `null`, trong khi ngoại lệ `explicit exception` của ví dụ vẫn hiển thị `required field`. Thông tin và câu chữ là chi tiết triển khai; không có cam kết chính xác trên mọi runtime.

Nếu stack trace báo `Unknown Source`, nguyên nhân có thể liên quan tới thông tin debug/source/line bị lược bỏ. Điều này không có nghĩa giá trị null không tồn tại; cần kết hợp bytecode, logs và dữ liệu đầu vào để chẩn đoán.

### 7.4. Giữ bí mật khi logging

Helpful message có thể nêu tên field, method và biến nội bộ. Giữ stack trace chi tiết trong **log nội bộ được phân quyền**; không gửi nguyên message/stack trace hoặc dữ liệu nhạy cảm lên giao diện công khai. Với khách hàng, trả mã lỗi/thông báo ứng dụng đã chuẩn hóa; nội bộ ghi thông tin cần thiết để tái hiện lỗi mà không lộ secrets.

## 8. Sửa nguyên nhân, không chỉ dập lỗi

### Trường bắt buộc phải tồn tại

Nếu miền dữ liệu yêu cầu địa chỉ không thể thiếu, hãy kiểm tra ngay trong constructor hoặc ranh giới tạo đối tượng:

```java
record Address(String city) {
    Address {
        java.util.Objects.requireNonNull(city, "city is required");
    }
}
```

Đây là **snippet minh họa độc lập**, không được thêm trùng khai báo `Address` vào file mẫu mục 5. Kiểm tra sớm giúp tránh NPE xuất hiện muộn khi nhiều lớp dữ liệu đã truyền object không hợp lệ qua lại.

### Trường có thể vắng mặt theo nghiệp vụ

Ví dụ khi khách hàng chưa nhập địa chỉ, đừng ép mọi customer phải có address. Có thể tách nhánh (snippet trong phương thức với `order` đã non-null):

```java
Customer customer = order.customer();
if (customer == null) {
    return "UNKNOWN";
}
Address address = customer.address();
if (address == null || address.city() == null) {
    return "UNKNOWN";
}
return address.city().toUpperCase(java.util.Locale.ROOT);
```

Nếu getter có thể trả kết quả thay đổi hoặc có side effect, lấy `String city = address.city();` một lần rồi kiểm tra biến `city`. Giá trị `UNKNOWN` ở đây **chỉ là quy ước ví dụ**, dùng thật phải theo đúng hợp đồng nghiệp vụ.

### Unboxing từ API trả nullable value

```java
java.util.Map<String, Integer> counts = java.util.Map.of();
Integer found = counts.get("sold");
int sold = found == null ? 0 : found;
```

Chỉ mặc định `0` nếu “không có giá trị” có nghĩa là “số lượng bằng 0”. Nếu vắng mặt là lỗi dữ liệu, kiểm tra và từ chối tường minh. Đừng tự động unbox `Integer` có thể null sang `int` rồi trông chờ Helpful NPE như một cơ chế validation.

### Khi kiểm thử

- Có case đầy đủ: `new Order(new Customer(new Address("Ha Noi")))` và phép gọi `upperCity(...)` trả `"HA NOI"`.
- Có case null ở từng cấp trong chuỗi, phần tử mảng null, và `Map.get` vắng mặt.
- Dùng `assertThrows(NullPointerException.class, ...)` khi ngoại lệ là hợp đồng mong đợi; **không** khóa assertion vào toàn bộ wording message của JVM.
- Với lỗi nghiệp vụ, test mã lỗi/thông điệp do ứng dụng **tự định nghĩa**; kết hợp trace/log hợp lệ để chẩn đoán runtime.
- Tránh `catch (NullPointerException e) { return null; }` như cách xử lý mặc định vì nó che nguyên nhân và có thể để lại dữ liệu sai.

## 9. Lỗi hiểu sai thường gặp

| Nhầm lẫn | Điều đúng |
|---|---|
| `Cannot invoke Address.city()` nghĩa là `city()` đã được thực thi và trả null | Không: receiver null ngăn **bắt đầu** lời gọi `city()` |
| Thông báo `return value of address() is null` nghĩa là `address()` đã ném NPE | Không: `address()` có thể trả `null` bình thường; **phép dùng kết quả đó** mới tạo NPE |
| JVM luôn tái tạo nguyên xi mọi ký tự của biểu thức source | JVM phân tích bytecode; tên local và hình thức mô tả có thể khác nhau |
| Chỉ cần `javac -g` là ứng dụng không còn NPE | `-g` chỉ thêm debug metadata; dữ liệu vẫn có thể null |
| Khi `getMessage() == null` thì không phải NPE thật | API cho phép message null; đọc exception type và stack trace |
| `Map.get()` luôn ném NPE khi khóa không tồn tại | Nó thường trả `null`; **auto-unboxing** mới là thao tác thất bại trong ví dụ |
| Đưa raw stack trace cho người dùng cuối giúp debug mà không có rủi ro | Message/trace có thể lộ thông tin nội bộ; cần kiểm soát quyền truy cập log |
| Dùng `Optional` ở mọi field là cách duy nhất tránh NPE | Thiết kế cần dựa trên hợp đồng nullability; kiểm tra bắt buộc, nhánh vắng mặt, immutable data hoặc Optional tại ranh giới khi phù hợp |

## 10. Checklist trước khi kết luận đã tìm được lỗi

1. Xác nhận `NullPointerException`, file và dòng từ stack trace.
2. Tách **thao tác thất bại** ở `Cannot ...` và **nguồn null** ở `because ... is null`.
3. Nếu có `return value of X()`, truy ngược dữ liệu đầu ra của `X()`.
4. Kiểm tra cả các bước ngầm của Java như **auto-unboxing**.
5. Phân biệt bản thân mảng null với phần tử mảng null.
6. Nếu thấy `<localN>`, xem debug info hoặc tách biểu thức thành biến để điều tra.
7. Nếu thiếu message, kiểm tra JDK/flag/loại ngoại lệ và dữ liệu stack trace.
8. Xác định null là hợp lệ hay vi phạm invariant, rồi sửa đúng nơi.
9. Thêm test đường thành công và các điểm thiếu dữ liệu; không phụ thuộc câu chữ JVM.
10. Giữ message kỹ thuật trong log nội bộ, không trả dữ liệu nhạy cảm ra ngoài.

## Tài liệu tham khảo chính thức

- OpenJDK, JEP 358 — *Helpful NullPointerExceptions* (Java 14): https://openjdk.org/jeps/358
- Oracle Java SE 17, *The java Command*, cờ `-XX:+ShowCodeDetailsInExceptionMessages`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle Java SE 26 API, `java.lang.NullPointerException`, lưu ý `getMessage()` có thể trả null: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NullPointerException.html
- Oracle Java SE 17 API, `Objects.requireNonNull`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)
- Oracle Java SE 17 API, `Map.get`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#get(java.lang.Object)
