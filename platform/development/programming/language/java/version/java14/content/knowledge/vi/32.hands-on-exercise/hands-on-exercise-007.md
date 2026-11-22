# Chẩn đoán NPE từ thao tác trường, mảng và unboxing trong Java

## 1. Mục tiêu thực hành và phạm vi hiện hành

**`NullPointerException` (NPE)** xảy ra khi code cần một **tham chiếu object không null**, nhưng giá trị thực tế lại là `null`. Trong ứng dụng Java, ba nhóm nguyên nhân đặc biệt thường gặp là:

1. **Thao tác trường (field):** đọc/ghi trường của object `null`, hoặc truy cập một trường trong chuỗi object mà một mắt xích là `null`.
2. **Thao tác mảng (array):** lấy `length`, đọc/ghi phần tử của tham chiếu mảng `null`, hoặc dùng một **phần tử tham chiếu** đang là `null`.
3. **Tự động unboxing:** Java cần chuyển `Integer`/`Boolean` và các wrapper object khác về kiểu primitive, nhưng wrapper đang là `null`.

Từ **Java 14**, JEP 358 *Helpful NullPointerExceptions* giúp HotSpot tạo thông báo giải thích **thao tác nào thất bại** và **biểu thức nào có giá trị null**. Từ **JDK 15**, tính năng này được bật mặc định trong HotSpot và vẫn được hỗ trợ ở Java 17 và các JDK hiện hành.

Bài này là **thực hành tổng hợp**: bạn vừa hiểu quy tắc Java, vừa tự tạo lỗi, đọc diagnostics từ JVM, đối chiếu bytecode, sửa lỗi và viết kiểm thử để ngăn tái phát. Ví dụ chính biên dịch được bằng **JDK 17 trở lên**, không dùng API preview, incubator, cú pháp hay cờ JVM lỗi thời. Có một chương trình Java hoàn chỉnh, lệnh `javac`/`java` và **stdout ổn định đã được kiểm thử**.

Sau bài học, bạn có thể:

- Đọc `NullPointerException` stack trace, phân biệt câu **“Cannot read field”**, **“Cannot assign field”**, **“Cannot load/store from array”**, **“Cannot read the array length”** và **“Cannot invoke Integer.intValue()/Boolean.booleanValue()”**.
- Chỉ ra **tham chiếu thực sự null**, thay vì chỉ nhìn vào cả một biểu thức dài.
- Phân biệt **mảng null**, **phần tử của mảng null** và **chỉ số mảng không hợp lệ**.
- Hiểu vì sao NPE có thể phát sinh từ một phép cộng, điều kiện `if` hay so sánh sử dụng wrapper, dù không có lời gọi phương thức nào xuất hiện trong source.
- Biết khi nào dùng guard, `Objects.requireNonNull`, fallback, validation ở boundary hoặc thiết kế lại hợp đồng dữ liệu.
- Phân biệt thông báo helpful NPE do JVM tạo với thông điệp được viết chủ động trong code.
- Kiểm thử loại exception và kết quả nghiệp vụ mà **không hardcode câu chữ NPE phụ thuộc JVM**.

## 2. Nhìn vào cơ chế thay vì đoán từ dòng code

Một dòng Java có thể có nhiều thao tác cần object:

```java
int size = order.customer.address.city.length();
```

Để tìm nguyên nhân, hỏi lần lượt:

1. `order` có null không? Nếu null, việc đọc trường `customer` thất bại.
2. Nếu `order` không null, `order.customer` có null không? Nếu null, việc đọc trường `address` thất bại.
3. Nếu customer tồn tại, `order.customer.address` có null không? Nếu null, việc đọc trường `city` thất bại.
4. Nếu address tồn tại, `city` có null không? Nếu null, lời gọi instance method `length()` thất bại.

Những NPE trên có thể xuất hiện ở **cùng một dòng source**, nhưng **khác bytecode instruction và khác biểu thức gây lỗi**. Helpful NPE từ HotSpot thường nêu chính xác thao tác ở điểm thất bại, nhờ phân tích bytecode. Không nên “sửa” bằng cách thêm một kiểm tra null ngẫu nhiên ở cuối chuỗi: hãy xác định biến nào được phép null theo contract và xử lý ở đúng vị trí.

Ví dụ thông điệp minh họa:

```text
Cannot read field "customer" because "order" is null
Cannot read field "address" because "order.customer" is null
Cannot read field "city" because "order.customer.address" is null
Cannot invoke "String.length()" because "order.customer.address.city" is null
```

**Các dòng trên là ví dụ diễn giải**, không phải một stdout cố định của một chương trình cụ thể. Tên kiểu đầy đủ, tên biến, đường dẫn biểu thức và dấu ngoặc phụ thuộc bytecode/debug metadata/phiên bản JVM. Dòng NPE thật phải được đối chiếu với stack trace và code đúng phiên bản build.

## 3. Bảng chẩn đoán nhanh ba nhóm lỗi

| Source/biểu thức | Tham chiếu null thực sự | Thao tác thất bại | Lỗi kỳ vọng |
| --- | --- | --- | --- |
| `profile.id` | `profile` | Đọc field của object | `NullPointerException` |
| `profile.id = 7` | `profile` | Ghi field của object | `NullPointerException` |
| `profile.address.city` | `profile.address` | Đọc field `city` | `NullPointerException` |
| `int[] a = null; a.length` | `a` | Lấy độ dài mảng | `NullPointerException` |
| `int[] a = null; a[0]` | `a` | Nạp phần tử mảng | `NullPointerException` |
| `int[] a = null; a[0] = 5` | `a` | Ghi phần tử mảng | `NullPointerException` |
| `Profile[] a = new Profile[1]; a[0].id` | `a[0]` | Đọc field của phần tử null | `NullPointerException` |
| `Integer x = null; int n = x` | `x` | Unboxing qua `intValue()` | `NullPointerException` |
| `Boolean b = null; if (b) ...` | `b` | Unboxing qua `booleanValue()` | `NullPointerException` |
| `int[] a = new int[0]; a[0]` | **Không null** | Chỉ số ngoài mảng | `ArrayIndexOutOfBoundsException` |

**Phân biệt cực kỳ quan trọng:** Mảng hợp lệ có length 1 nhưng phần tử tham chiếu chưa gán vẫn có giá trị mặc định `null`. Còn mảng primitive như `int[]` chứa giá trị `0` mặc định cho phần tử, **không** chứa `null` ở từng slot. `int[]` bản thân mảng vẫn có thể là `null` nếu biến tham chiếu không trỏ tới một array object.

## 4. Truy cập trường: đọc, ghi và đi qua object chain

### 4.1. Đọc field khi receiver null

```java
Profile profile = null;
int id = profile.id; // NPE ở thao tác đọc field id
```

Đây là **đoạn minh họa trong một method**, giả sử `Profile` có một instance field tên `id`. Việc `id` thuộc kiểu primitive `int` **không cứu được** biểu thức: JVM cần một object `Profile` hợp lệ trước khi đọc giá trị từ field.

Helpful message ở HotSpot có thể bắt đầu bằng:

```text
Cannot read field "id" because "profile" is null
```

Nếu bạn thấy `Cannot read field "id"`, hãy tìm **receiver của field access**, không phải kiểm tra `id` có “null” không — primitive `int` không thể null.

### 4.2. Ghi field khi receiver null

```java
Profile profile = null;
profile.id = 7; // NPE trước khi ghi vào instance nào
```

Có thể nhận:

```text
Cannot assign field "id" because "profile" is null
```

Không có một instance object hợp lệ để chứa `id=7`. Đây là **field assignment**, không phải vấn đề giá trị `7`.

### 4.3. Null ở giữa chuỗi truy cập

```java
Profile profile = new Profile();
String city = profile.address.city;
```

Ở đây `profile` tồn tại, nhưng `address` mặc định `null`. Vì vậy:

```text
Cannot read field "city" because "profile.address" is null
```

Thông báo nêu **`profile.address`** là biểu thức null, không buộc bạn sửa bằng cách đặt `profile = new Profile()` lần nữa.

Để khắc phục đúng, cần xác định **address là dữ liệu bắt buộc hay tùy chọn**:

- Nếu **bắt buộc**, constructor/DTO validation nên từ chối Profile không có address.
- Nếu **tùy chọn**, nhánh hiển thị có thể dùng fallback `"unknown"`, nhưng chỉ khi contract thật sự cho phép.
- Nếu vừa bị xóa bởi luồng khác, cần phân tích concurrency/lifecycle; một phép `if (address != null)` ở đầu phương thức không luôn đủ an toàn nếu reference có thể thay đổi trong lúc chạy.

### 4.4. Static field không giống instance field

`Profile.staticCount` là access tới **static field của class**, không cần instance `Profile`. Đừng đồng nhất mọi dấu chấm trong Java với việc dereference một object; cần biết field là static hay instance. Việc dùng cú pháp thông qua instance để truy cập static member là cách viết gây hiểu nhầm và nên tránh.

## 5. Mảng: phân biệt null array, null element và index error

### 5.1. Tham chiếu mảng null

```java
int[] numbers = null;

int count = numbers.length; // NPE
int first = numbers[0];     // NPE
numbers[0] = 9;             // NPE
```

Ba dòng gây lỗi **độc lập** và phải chạy riêng từng tình huống trong test: nếu chạy nối tiếp mà không catch, chương trình dừng ngay tại dòng đầu tiên.

HotSpot có thể mô tả:

```text
Cannot read the array length because "numbers" is null
Cannot load from int array because "numbers" is null
Cannot store to int array because "numbers" is null
```

Các thông điệp trên mô tả **loại thao tác mảng thất bại**. Tên `int` sẽ khác nếu đó là `double[]`, `Object[]` hoặc kiểu mảng khác.

### 5.2. Array object tồn tại nhưng element là null

```java
Profile[] profiles = new Profile[1];
int id = profiles[0].id; // NPE vì profiles[0] == null
```

- `profiles != null`.
- `profiles.length == 1`.
- Chỉ số `0` **hợp lệ**.
- Nhưng `profiles[0] == null` vì chưa gán một `Profile` object.
- Đọc field `id` của **phần tử null** mới là bước gây NPE.

Thông điệp có thể là:

```text
Cannot read field "id" because "profiles[0]" is null
```

Vì vậy câu khẳng định “mảng đã `new` thì không thể NPE” là sai.

### 5.3. Mảng không null nhưng index sai

```java
int[] empty = new int[0];
int first = empty[0]; // ArrayIndexOutOfBoundsException
```

Khác với NPE: receiver là mảng hợp lệ, nhưng index 0 nằm ngoài đoạn hợp lệ vì length 0. Kiểm tra **`array != null`** không thay thế kiểm tra **`0 <= index && index < array.length`**.

Với mảng nhiều chiều:

```java
String[][] table = new String[2][];
String value = table[0][0]; // NPE: table[0] == null
```

Dù `table` có hai phần tử, mỗi phần tử là tham chiếu `String[]` đang null. Cần tạo từng mảng con hoặc xác định hợp đồng “hàng null” được phép hay không.

### 5.4. null và `for-each`

```java
int[] numbers = null;
for (int value : numbers) {
    System.out.println(value);
}
```

Dạng `for-each` trên array cần array object để đọc length và phần tử. Nếu biến mảng `null`, chương trình có thể NPE ở code sinh ra từ vòng lặp. Trên source, bạn không thấy `numbers.length`, nhưng bytecode vẫn thực hiện thao tác array.

**Không biến null thành empty array một cách tùy tiện:** Trong một số API, `null` nghĩa là **dữ liệu chưa tải**, khác hoàn toàn với “danh sách rỗng”. Nếu contract nói luôn trả collection, thiết kế trả một empty collection thay vì null; nếu null mang ý nghĩa nghiệp vụ, phải xử lý rõ trạng thái đó.

## 6. Unboxing: NPE xuất hiện dù source không gọi method

**Unboxing** là chuyển từ wrapper object như `Integer` sang primitive `int`, hoặc `Boolean` sang `boolean`. Java có thể tự thêm thao tác gọi `intValue()` hoặc `booleanValue()` ở bytecode.

### 6.1. Gán wrapper vào primitive

```java
Integer visits = null;
int count = visits; // NPE khi JVM cần gọi Integer.intValue()
```

Một thông báo helpful NPE có thể viết:

```text
Cannot invoke "java.lang.Integer.intValue()" because "visits" is null
```

Tại sao source chỉ là `int count = visits` mà thông báo lại có `intValue()`? Vì compiler đã chèn một lời gọi unboxing tương đương để thu primitive value. Việc không thấy method call trong source **không có nghĩa không có invoke trong bytecode**.

### 6.2. Wrapper nằm trong field

```java
Profile profile = new Profile(); // visits mặc định null
int count = profile.visits;      // NPE ở unboxing
```

`profile` là object hợp lệ, thao tác đọc field `visits` **thành công và trả null**. NPE không nổ khi đọc field, mà xảy ra khi dùng wrapper null như `int`.

Có thể thấy:

```text
Cannot invoke "java.lang.Integer.intValue()" because "profile.visits" is null
```

Đừng vội kết luận `profile` null. Thông báo nói rõ **field wrapper** đang null.

### 6.3. Wrapper nằm trong mảng

```java
Integer[] visits = {null};
int total = visits[0] + 1;
```

Array object tồn tại, index hợp lệ; phần tử `visits[0]` lại là wrapper null. Trong phép cộng số học, Java cần primitive `int` nên gây NPE:

```text
Cannot invoke "java.lang.Integer.intValue()" because "visits[0]" is null
```

Nếu thay bằng `int[]` và phần tử chưa gán, giá trị mặc định là 0 nên không có unboxing.

### 6.4. Boolean wrapper trong if

```java
Boolean enabled = null;

if (enabled) {
    System.out.println("enabled");
}
```

Điều kiện `if` yêu cầu primitive boolean, vì vậy compiler unbox `Boolean` và có thể tạo thông điệp:

```text
Cannot invoke "java.lang.Boolean.booleanValue()" because "enabled" is null
```

Không có một trạng thái Java primitive `boolean` thứ ba tên là null. Nếu domain yêu cầu **ba trạng thái** (true/false/unknown), hãy xử lý rõ cả ba thay vì ép `Boolean` null sang `boolean`.

### 6.5. Unboxing “ẩn” trong nhiều biểu thức

Các ví dụ thường gặp:

```java
Integer quantity = null;

boolean positive = quantity > 0;   // NPE, unboxing để so sánh
int total = quantity + 10;         // NPE, unboxing để cộng
int repeated = Math.max(quantity, 1); // NPE, unboxing làm argument
```

Mỗi dòng là một **ví dụ lỗi độc lập**, không phải đoạn code dự kiến chạy tuần tự. `Math.max(int,int)` nhận primitive nên lời gọi có thể cần unboxing `quantity`.

Một trường hợp từ dữ liệu lookup:

```java
Map<String, Integer> bySku = new HashMap<>();
int count = bySku.get("missing"); // NPE khi unbox null
```

Đoạn này cần import `java.util.Map` và `java.util.HashMap`. `Map.get` có thể trả null khi key không tồn tại **hoặc** key được map tới giá trị null. Vì vậy không dùng `int` nhận trực tiếp kết quả `get` nếu contract không đảm bảo một `Integer` khác null.

## 7. Đọc Helpful NullPointerException của HotSpot

### 7.1. Mẫu thông điệp

Thông báo thường có dạng:

```text
Cannot <failed operation> because "<null expression>" is null
```

Mảnh `<failed operation>` mô tả thao tác JVM đang thực hiện, ví dụ:

- `read field "id"` / `assign field "id"`;
- `read the array length`;
- `load from int array` / `store to int array`;
- `invoke "java.lang.Integer.intValue()"`;
- `invoke "java.lang.Boolean.booleanValue()"`.

Mảnh `<null expression>` cố gắng tái tạo biểu thức nhận ra từ bytecode, ví dụ `profile`, `profile.address`, `profiles[0]`, `visits[0]` hoặc return value của một method call.

**Giới hạn:** Đây là thông báo chẩn đoán được JVM tạo, **không phải API để máy phân tích cú pháp bằng một grammar bất biến**. Chính xác tên biến/kiểu/đường dẫn source tùy thông tin trong class file, cấu trúc bytecode và VM implementation.

### 7.2. Tùy chọn JVM hiện hành

Trên HotSpot Java 17+ có thể chạy:

```bash
java -XX:+ShowCodeDetailsInExceptionMessages NpeDiagnosticsDemo --details
```

Flag `-XX:+ShowCodeDetailsInExceptionMessages` cho phép JVM phân tích bytecode để tạo thông điệp chi tiết khi NPE **phát sinh từ dereference/unboxing trong VM**. Trong HotSpot từ Java 15, cờ này **bật mặc định**, nên trên JVM tiêu chuẩn thường không cần thêm; ghi cờ dương trong bài thực hành chỉ để làm rõ mục đích.

Muốn minh họa khi tắt:

```bash
java -XX:-ShowCodeDetailsInExceptionMessages NpeDiagnosticsDemo --details
```

Khi tắt, các NPE do VM tạo thường không có thông điệp helpful và `getMessage()` có thể trả null. Nhưng một NPE được **ném chủ động với chuỗi message riêng** vẫn có message từ constructor/`Objects.requireNonNull` theo code ứng dụng.

**Không khuyến nghị tắt ở production** chỉ để log ngắn hơn: bạn mất thông tin chẩn đoán hữu ích. Nếu muốn kiểm soát dữ liệu log, hãy xử lý tại logging/tracing policy thay vì mặc định vô hiệu hóa diagnostics.

### 7.3. Nguồn gốc tên biến: LocalVariableTable

Biên dịch với:

```bash
javac --release 17 -g NpeDiagnosticsDemo.java
```

`-g` yêu cầu compiler phát hành **thông tin debug đầy đủ**, gồm tên biến cục bộ và parameter trong `LocalVariableTable`. Nếu không có thông tin này, HotSpot vẫn có thể mô tả thao tác NPE nhưng phần biểu thức null có thể hiện thành `<local1>`, `<parameter1>` hoặc dạng tương tự.

Theo `javac`, mặc định thường có **line numbers** và **source file metadata**, còn local variable names đòi `-g` hoặc `-g:vars`. Nếu muốn giữ tên biến cùng line/source, `-g` là lựa chọn dễ hiểu trong bài học.

**Tránh lạm dụng:** Có debug info không đồng nghĩa JDK đảm bảo mọi message phải chứa chính xác tên biến gốc; compiler/JIT/bytecode transformations có thể thay đổi đường đi. Một chương trình đóng gói, tối ưu hoặc instrument bởi agent cũng có thể có class file khác source IDE.

### 7.4. Helpful NPE không phải một NPE do ứng dụng tự tạo

`Objects.requireNonNull(profile, "profile is required")` ném NPE từ thư viện với **message chủ động do developer truyền**. Nó không được tạo ra bằng cùng cơ chế phân tích bytecode truy cập field.

```java
Profile safe = Objects.requireNonNull(
        profile, "profile is required");
```

Đoạn này giả định `profile` có thể null và `Profile` được khai báo. Nếu profile null, message có thể là **`profile is required`** vì đó là text người viết code sở hữu, chứ không phải một câu `Cannot read field ...` tự phân tích từ JVM.

NPE tự tạo qua `new NullPointerException("...")` cũng có semantics message tương tự.

### 7.5. Khi helpful message không có

Theo Javadoc Java 17/26, `NullPointerException.getMessage()` trả một chuỗi hoặc null. Helpful detail chỉ có thể tạo **khi internal information còn sẵn**. Trường hợp **deserialize một NullPointerException object** không giữ dữ liệu nội bộ cần để tái tạo helpful message.

Vì vậy nếu log chỉ ghi `java.lang.NullPointerException` mà không có `Cannot ...`, đừng kết luận app không có NPE thật. Kiểm tra:

- JVM version/vendor và cấu hình `ShowCodeDetailsInExceptionMessages`.
- NPE do JVM tự tạo hay do source chủ động ném.
- Class file chứa debug info, stack trace còn đủ thông tin hay không.
- Việc exception được bọc, serialize/deserialze, hoặc log chỉ hiện message rỗng.
- Khả năng stack trace bị rút gọn hoặc thông điệp bị hệ thống logging lọc.

**Không lấy `getMessage().contains("profile")` làm điều kiện nghiệp vụ**. Kiểm tra **exception type** và hành vi API của bạn thay vì parse câu chữ nội bộ của JVM.

## 8. Ví dụ Java 17+ đầy đủ: 12 NPE, một đối chứng và ba ca an toàn

Tạo duy nhất file **`NpeDiagnosticsDemo.java`** dưới đây. Chương trình có hai chế độ:

- `java NpeDiagnosticsDemo`: **chỉ in nhãn + loại exception**, cho stdout xác định trên JDK 17+.
- `java NpeDiagnosticsDemo --details`: in thêm `ex.getMessage()` của từng NPE để xem cách **JVM thực tế** mô tả tham chiếu null; các dòng này **phụ thuộc environment**.

Các phép NPE được đưa vào method riêng và chạy trong hàm `expectNpe`, để chương trình không dừng ngay ở lỗi đầu tiên. Nếu có một ca **không ném** NPE như kỳ vọng, helper sẽ tạo `AssertionError` thay vì lặng lẽ ghi nhận thành công.

```java
import java.util.Objects;

public final class NpeDiagnosticsDemo {
    private static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    private static final class Profile {
        int id;
        Address address;
        Integer visits;
    }

    private NpeDiagnosticsDemo() {
    }

    private static void expectNpe(
            String label, Runnable operation, boolean details) {
        try {
            operation.run();
            throw new AssertionError(
                    "Expected NullPointerException: " + label);
        } catch (NullPointerException ex) {
            System.out.println(label + "=NullPointerException");
            if (details) {
                System.out.println("  message=" + ex.getMessage());
            }
        }
    }

    private static void expectIndexException() {
        try {
            int[] values = new int[0];
            int result = values[0];
            throw new AssertionError(
                    "Unexpected result: " + result);
        } catch (ArrayIndexOutOfBoundsException expected) {
            System.out.println(
                    "array-index=ArrayIndexOutOfBoundsException");
        }
    }

    private static void fieldRead() {
        Profile profile = null;
        int id = profile.id;
        System.out.println(id);
    }

    private static void fieldWrite() {
        Profile profile = null;
        profile.id = 7;
    }

    private static void nestedField() {
        Profile profile = new Profile();
        String city = profile.address.city;
        System.out.println(city);
    }

    private static void arrayLength() {
        int[] values = null;
        int length = values.length;
        System.out.println(length);
    }

    private static void arrayRead() {
        int[] values = null;
        int item = values[0];
        System.out.println(item);
    }

    private static void arrayWrite() {
        int[] values = null;
        values[0] = 9;
    }

    private static void arrayElementField() {
        Profile[] profiles = new Profile[1];
        int id = profiles[0].id;
        System.out.println(id);
    }

    private static void unboxLocal() {
        Integer visits = null;
        int number = visits;
        System.out.println(number);
    }

    private static void unboxField() {
        Profile profile = new Profile();
        int number = profile.visits;
        System.out.println(number);
    }

    private static void unboxArray() {
        Integer[] visits = {null};
        int number = visits[0] + 1;
        System.out.println(number);
    }

    private static void unboxBoolean() {
        Boolean enabled = null;
        if (enabled) {
            System.out.println("enabled");
        }
    }

    private static int safeLength(int[] array) {
        return array == null ? 0 : array.length;
    }

    private static int safeVisits(Integer visits) {
        return visits == null ? 0 : visits;
    }

    private static String safeCity(Profile profile) {
        if (profile == null || profile.address == null) {
            return "unknown";
        }
        return profile.address.city == null
                ? "unknown"
                : profile.address.city;
    }

    public static void main(String[] args) {
        if (args.length > 1 ||
                (args.length == 1
                && !"--details".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: NpeDiagnosticsDemo [--details]");
        }

        boolean details = args.length == 1;

        expectNpe("field-read",
                NpeDiagnosticsDemo::fieldRead, details);
        expectNpe("field-write",
                NpeDiagnosticsDemo::fieldWrite, details);
        expectNpe("nested-field",
                NpeDiagnosticsDemo::nestedField, details);
        expectNpe("array-length",
                NpeDiagnosticsDemo::arrayLength, details);
        expectNpe("array-read",
                NpeDiagnosticsDemo::arrayRead, details);
        expectNpe("array-write",
                NpeDiagnosticsDemo::arrayWrite, details);
        expectNpe("array-element-field",
                NpeDiagnosticsDemo::arrayElementField, details);
        expectNpe("unbox-local",
                NpeDiagnosticsDemo::unboxLocal, details);
        expectNpe("unbox-field",
                NpeDiagnosticsDemo::unboxField, details);
        expectNpe("unbox-array",
                NpeDiagnosticsDemo::unboxArray, details);
        expectNpe("unbox-boolean",
                NpeDiagnosticsDemo::unboxBoolean, details);
        expectNpe("explicit-precondition",
                () -> Objects.requireNonNull(
                        (Profile) null, "profile is required"),
                details);

        expectIndexException();

        System.out.println(
                "safe-length=" + safeLength(null));
        System.out.println(
                "safe-visits=" + safeVisits(null));

        Profile valid = new Profile();
        valid.address = new Address("Hue");
        System.out.println("safe-city=" + safeCity(valid));
    }
}
```

### Biên dịch và chạy

Với **JDK 17 trở lên**:

```bash
javac --release 17 -g NpeDiagnosticsDemo.java
java NpeDiagnosticsDemo
```

**Stdout chính xác đã được kiểm thử** của chế độ mặc định:

```text
field-read=NullPointerException
field-write=NullPointerException
nested-field=NullPointerException
array-length=NullPointerException
array-read=NullPointerException
array-write=NullPointerException
array-element-field=NullPointerException
unbox-local=NullPointerException
unbox-field=NullPointerException
unbox-array=NullPointerException
unbox-boolean=NullPointerException
explicit-precondition=NullPointerException
array-index=ArrayIndexOutOfBoundsException
safe-length=0
safe-visits=0
safe-city=Hue
```

Tất cả nhãn được xác định bởi code; không phụ thuộc thứ tự bất định, timestamp, số ngẫu nhiên, hệ điều hành hay một thông báo NPE do HotSpot sinh ra. Chương trình đã được **biên dịch với `javac --release 17 -g` và chạy thực tế** trên một JDK hỗ trợ Java 17+ để kiểm chứng stdout.

### Chạy chế độ chẩn đoán chi tiết

```bash
java -XX:+ShowCodeDetailsInExceptionMessages NpeDiagnosticsDemo --details
```

Ở một lần kiểm thử với **HotSpot JDK 21**, các dòng message thu được như sau; **đây là mẫu quan sát, không phải text được Java SE cam kết ổn định**:

```text
field-read=NullPointerException
  message=Cannot read field "id" because "profile" is null
field-write=NullPointerException
  message=Cannot assign field "id" because "profile" is null
nested-field=NullPointerException
  message=Cannot read field "city" because "profile.address" is null
array-length=NullPointerException
  message=Cannot read the array length because "values" is null
array-read=NullPointerException
  message=Cannot load from int array because "values" is null
array-write=NullPointerException
  message=Cannot store to int array because "values" is null
array-element-field=NullPointerException
  message=Cannot read field "id" because "profiles[0]" is null
unbox-local=NullPointerException
  message=Cannot invoke "java.lang.Integer.intValue()" because "visits" is null
unbox-field=NullPointerException
  message=Cannot invoke "java.lang.Integer.intValue()" because "profile.visits" is null
unbox-array=NullPointerException
  message=Cannot invoke "java.lang.Integer.intValue()" because "visits[0]" is null
unbox-boolean=NullPointerException
  message=Cannot invoke "java.lang.Boolean.booleanValue()" because "enabled" is null
explicit-precondition=NullPointerException
  message=profile is required
array-index=ArrayIndexOutOfBoundsException
safe-length=0
safe-visits=0
safe-city=Hue
```

Trên JDK/vendor khác, tên biến, kiểu đầy đủ và wording có thể khác; nếu details bị tắt, nhiều dòng `message=...` của VM-generated NPE có thể thành `message=null`. **Chỉ stdout không có `--details` mới là mẫu cố định để đối chiếu nguyên văn.**

### Những gì chương trình đã thực sự chứng minh

- **`field-read`**: object `profile` không tồn tại, đọc `id` gây NPE.
- **`field-write`**: ghi `id=7` qua receiver null cũng gây NPE.
- **`nested-field`**: `profile` tồn tại, nhưng `profile.address` null; lỗi ở truy cập field `city`.
- **`array-length`**, **`array-read`**, **`array-write`**: ba loại thao tác khác nhau trên **chính array reference null**.
- **`array-element-field`**: array tồn tại, index hợp lệ, nhưng phần tử `profiles[0]` null.
- **`unbox-local`**, **`unbox-field`**, **`unbox-array`**: Java chèn unboxing `Integer.intValue()` từ wrapper null.
- **`unbox-boolean`**: điều kiện `if` cần `Boolean.booleanValue()`, wrapper null gây NPE.
- **`explicit-precondition`**: NPE có **message viết chủ động** `profile is required`, không phải thông báo phân tích bytecode.
- **`array-index`**: đối chứng một array không null nhưng index sai, phát `ArrayIndexOutOfBoundsException`.
- **`safe-length`/`safe-visits`/`safe-city`**: ba ví dụ xử lý null có fallback **chỉ dành cho contract demo**; không tự áp đặt fallback 0/unknown lên số tiền, số đơn hàng hoặc thông tin bắt buộc của hệ thống thật.

## 9. Đọc stack trace để tìm nơi phát sinh thay vì chỉ đọc message

Một NPE không được bắt sẽ có stack trace đại loại:

```text
Exception in thread "main" java.lang.NullPointerException:
  Cannot read field "city" because "profile.address" is null
    at NpeDiagnosticsDemo.nestedField(NpeDiagnosticsDemo.java:<line>)
    at NpeDiagnosticsDemo.expectNpe(NpeDiagnosticsDemo.java:<line>)
    at NpeDiagnosticsDemo.main(NpeDiagnosticsDemo.java:<line>)
```

Đây là **mẫu minh họa cấu trúc** với `<line>` thay cho số dòng phụ thuộc cách dán file vào editor; không phải stdout của chương trình mặc định, vốn **đã bắt các NPE** để tiếp tục các ca kiểm thử.

Cách đọc:

1. **Exception type:** `java.lang.NullPointerException` — loại lỗi.
2. **Message:** thao tác nào thất bại, receiver nào null.
3. **Frame đầu tiên hữu ích:** vị trí code thực sự truy cập field/array/unboxing.
4. **Các frame phía dưới:** đường gọi khiến dữ liệu null đi đến đó.
5. **Giá trị đầu vào:** request/DTO/response/database row nào đã khiến invariant bị vi phạm.
6. **Thời điểm và context:** thread nào, phiên bản binary nào, dữ liệu có bị mutation giữa các bước không.

**Không chỉ tìm chuỗi "NPE" trong log**: một framework có thể bọc NPE thành một exception khác, còn một message user-defined có thể chứa “null” nhưng type không phải `NullPointerException`. Khi có `Caused by`, đọc theo **cause chain** và frame của code ứng dụng.

### Bài luyện stack trace với chẩn đoán hợp lệ

Giả sử thấy:

```text
Cannot invoke "java.lang.Integer.intValue()" because "order.quantity" is null
```

Câu hỏi nên đặt: **Vì sao `order.quantity` là Integer null?** Có phải field chưa khởi tạo, DB column nullable, mapping JSON thiếu giá trị hay một phép lookup trả null? Không nên kết luận `order` null, vì receiver `order` đã được truy cập thành công để đọc field `quantity`.

## 10. Dùng javap đối chiếu Java source với bytecode

Helpful NPE mô tả những operation ở **bytecode level**, nên bạn có thể xem disassembly:

```bash
javap -c -p NpeDiagnosticsDemo
```

Tùy compiler và cách optimize, bạn sẽ thấy nhóm instruction:

| Bytecode | Ý nghĩa | NPE khi nào? |
| --- | --- | --- |
| `getfield` | Đọc instance field | Receiver object null |
| `putfield` | Ghi instance field | Receiver object null |
| `arraylength` | Đọc length của array | Array reference null |
| `iaload` | Đọc phần tử của `int[]` | Array reference null |
| `iastore` | Ghi phần tử vào `int[]` | Array reference null |
| `aaload` | Đọc phần tử của reference array | **Array null** gây NPE ngay; nếu array tồn tại và phần tử null thì bản thân `aaload` trả null |
| `invokevirtual Integer.intValue()` | Unbox `Integer` | Wrapper receiver null |
| `invokevirtual Boolean.booleanValue()` | Unbox `Boolean` | Wrapper receiver null |

**Sự phân biệt cốt lõi:** Với `profiles[0].id`, bytecode đọc element bằng `aaload` **thành công** (trả null), sau đó `getfield` gây NPE. Với `int[] values = null; values[0]`, bytecode `iaload` gây NPE ngay vì **array receiver** là null.

Lý do helpful NPE có thể nói `Cannot invoke Integer.intValue()` trong một phép `+` là compiler đã chèn lời gọi unboxing. Bạn không cần viết method `intValue()` ở source.

**Không cần kiểm tra bytecode cho mọi NPE đơn giản trong production.** Hãy dùng `javap` khi thông điệp khó hiểu, có bytecode instrumentation, generics/bridge methods, framework-generated classes hoặc code được compiler chuyển đổi phức tạp.

## 11. Sửa lỗi theo hợp đồng dữ liệu, không chỉ “chặn NPE”

### 11.1. Trường bắt buộc: fail early ở boundary

Nếu `Profile.address` là bắt buộc, hãy kiểm tra khi tạo object:

```java
import java.util.Objects;

public record ProfileDto(String id, AddressDto address) {
    public ProfileDto {
        Objects.requireNonNull(id, "id is required");
        Objects.requireNonNull(
                address, "address is required");
    }
}

record AddressDto(String city) {
    AddressDto {
        Objects.requireNonNull(
                city, "city is required");
    }
}
```

Đây là **ví dụ minh họa gồm các record type ở mức file**, cần đặt mỗi `public` top-level class vào file cùng tên hoặc chỉnh visibility thích hợp khi thử. Record là tính năng Java ổn định từ Java 16, phù hợp **JDK 17+**. Không cần record nếu dự án dùng POJO; quan trọng là kiểm tra invariant.

Cách này giúp phát hiện dữ liệu thiếu **tại lúc dựng object** thay vì phát NPE sâu trong chuỗi truy cập. Thông điệp từ `Objects.requireNonNull` là message do ứng dụng đặt, phù hợp với contract hơn so với một câu bytecode diagnostics nếu bạn cần trả lỗi cho client.

### 11.2. Trường tùy chọn: guard rõ ràng

Nếu `address` có thể vắng mặt theo thiết kế:

```java
String city;
if (profile == null || profile.address == null
        || profile.address.city == null) {
    city = "unknown";
} else {
    city = profile.address.city;
}
```

Đây là đoạn minh họa cho class `Profile` với fields tương ứng. Fallback `"unknown"` chỉ đúng **nếu business contract cho phép**. Khi thông tin bắt buộc, thay bằng validation và lỗi nghiệp vụ rõ ràng.

Khi object có thể bị mutate đồng thời, đọc một snapshot/biến cục bộ rồi kiểm tra để tránh một thread xóa field giữa hai lần truy cập. Tùy mô hình concurrency, bạn còn cần synchronization/immutable data và các quy tắc visibility; chỉ guard null không thay concurrency correctness.

### 11.3. Mảng: validate reference và index độc lập

```java
static int safeRead(int[] values, int index) {
    Objects.requireNonNull(values, "values is required");
    if (index < 0 || index >= values.length) {
        throw new IndexOutOfBoundsException(
                "index out of range: " + index);
    }
    return values[index];
}
```

Đây là **method minh họa** cần import `java.util.Objects` và đặt trong một class. Nó có hai điều kiện kiểm tra khác nhau:

1. Mảng phải tồn tại.
2. Index phải thuộc đoạn `[0, values.length)`.

Có thể chủ động dùng `Objects.checkIndex(index, values.length)` trên Java hiện hành để thay kiểm tra index thủ công, **sau khi** đã quyết định cách xử lý mảng null. Không coi NPE và AIOOBE là cùng một lỗi.

### 11.4. Wrapper: không tự default về zero nếu thiếu dữ liệu là lỗi

Nếu contract cho phép “không có số lượt truy cập nghĩa là 0”:

```java
Integer visits = null;
int count = visits == null ? 0 : visits;
```

Nếu contract yêu cầu visits luôn có giá trị:

```java
Integer visits = loadVisitCount();
int count = Objects.requireNonNull(
        visits, "visitCount is required");
```

Đây là mã minh họa trong một method có hàm `loadVisitCount()` do ứng dụng cung cấp. Không nên dùng `0` nếu điều đó sẽ che lỗi thiếu dữ liệu nghiệp vụ, đặc biệt với giá, số lượng, quyền duyệt hoặc trạng thái tài chính.

Với `Boolean` ba trạng thái:

```java
Boolean accepted = loadApproval();

if (Boolean.TRUE.equals(accepted)) {
    // Chỉ true thực sự mới vào nhánh.
}
```

Hàm `loadApproval()` là stub mô tả. `Boolean.TRUE.equals(null)` trả false và **không unbox null**. Nếu `null` mang nghĩa “chưa quyết định”, bạn cần **một nhánh riêng** để xử lý thay vì đồng nhất unknown với false.

### 11.5. Map.get() và Optional

`Map.get(key)` trả null nếu không có mapping, và cũng có thể trả null khi mapping tồn tại với value null. Do đó:

```java
Integer countBoxed = countsById.get(id);
if (countBoxed == null) {
    throw new IllegalArgumentException(
            "Missing count for id=" + id);
}
int count = countBoxed;
```

Đây là đoạn **minh họa** với `Map<?, Integer> countsById` và `id` có sẵn. Nếu muốn phân biệt **key thiếu** với **key có value null**, dùng `containsKey` cùng logic tương ứng.

`getOrDefault(key, 0)` chỉ trả default khi **không có mapping**, không tự thay thế mọi mapping có **giá trị null**. Đừng dùng nó để khắc phục NPE khi Map cho phép value null mà chưa kiểm tra contract.

`Optional.ofNullable(value)` có thể biểu diễn giá trị vắng mặt ở một boundary/API, nhưng không nên dùng `Optional.get()` vô điều kiện: lúc không có giá trị sẽ gây `NoSuchElementException`, không giải quyết vấn đề về hợp đồng dữ liệu.

## 12. Bảo mật và vận hành với Helpful NPE

Helpful NPE mô tả **biểu thức, tên field/method, class và đường gọi**. Những thông tin này hữu ích trong log nội bộ, nhưng không nên trả nguyên stack trace/chi tiết implementation ra API công khai cho mọi người dùng. Việc có NPE không có nghĩa log dữ liệu object sẽ an toàn: một logging framework có thể thêm request parameters, headers hoặc dữ liệu nhạy cảm ở nơi khác.

Thực hành khuyến nghị:

- Ở **server/API boundary**, chuyển lỗi bất ngờ thành response lỗi chuẩn của ứng dụng, có correlation ID, và log stack trace ở kênh nội bộ theo chính sách.
- Ở **unit test**, assert đúng loại exception hoặc contract, không so khớp nguyên văn message JVM. Chỉ assert message khi **chính API ứng dụng cam kết thông điệp đó**.
- **Không catch NPE toàn hệ thống rồi tiếp tục như không có gì**, vì nó có thể chỉ ra invariant bị vi phạm và dữ liệu đang thiếu.
- Không dùng NPE như một nhánh điều khiển thông thường cho input hợp lệ có thể thiếu; validate ở boundary và mô hình hóa optionality rõ ràng.
- Có thể thu stack trace đầy đủ khi chẩn đoán, nhưng không đưa class/field names và dữ liệu người dùng vào response public ngoài nhu cầu.
- Nếu lỗi xảy ra không thường xuyên trong môi trường nhiều thread, thu thêm context race/synchronization. NPE message chỉ mô tả trạng thái dereference **tại thời điểm lỗi**, không chỉ ra trực tiếp ai đã gán null.
- Một ngoại lệ được ghi lại nhiều lần có thể bị framework rút gọn log; đảm bảo logging policy giữ được ít nhất các frame căn bản cho điều tra.

## 13. Phân loại lỗi dễ bị nhầm

| Lỗi | Bản chất | Ví dụ |
| --- | --- | --- |
| `NullPointerException` | Dereference hoặc unboxing một reference null | `Integer x=null; int y=x` |
| `ArrayIndexOutOfBoundsException` | Array tồn tại nhưng index ngoài phạm vi | `new int[0][0]` không phải ví dụ đúng: dùng `int[] a = new int[0]; a[0]` |
| `ClassCastException` | Cast object sang kiểu không tương thích | `(String) Integer.valueOf(1)` qua reference có kiểu phù hợp khi biên dịch |
| `NoSuchElementException` | Truy xuất phần tử không tồn tại qua API như `Optional.get()` | `Optional.empty().get()` |
| `IllegalArgumentException` | API chủ động từ chối argument theo contract | `throw new IllegalArgumentException("bad id")` |
| `IllegalStateException` | API chủ động từ chối state hiện tại | `throw new IllegalStateException("not initialized")` |

Một số đoạn trong bảng chỉ để mô tả cơ chế, không phải file có thể biên dịch độc lập. Đặc biệt `new int[0][0]` tạo mảng hai chiều hợp lệ, **không** phải cách minh họa `ArrayIndexOutOfBoundsException`; lỗi index chuẩn là `new int[0]` rồi truy cập `[0]`.

Phân loại đúng giúp bạn sửa **root cause**, không cố xử lý mọi lỗi runtime bằng một `catch (RuntimeException e)` chung và trả default tùy tiện.

## 14. Quy trình chẩn đoán thực tế trong dự án

Khi nhận một NPE trong hệ thống:

### Bước 1 — Xác minh build và môi trường

Ghi `java -version`, JDK vendor, ứng dụng build SHA/version, cấu hình cờ JVM. Đảm bảo source bạn đang đọc thực sự khớp binary đang chạy; lệch dòng source sau deploy khiến bạn điều tra sai.

### Bước 2 — Đọc stack trace và thông báo helpful

Tìm class, method, line number đầu tiên liên quan code của bạn; đọc phần `Cannot ... because ... is null` nếu có. Chia biểu thức dài thành từng receiver và xác định **chỗ null thực sự**.

### Bước 3 — Nhận diện nhóm thao tác

- `Cannot read/assign field` → field receiver null.
- `Cannot read the array length` → array reference null.
- `Cannot load/store from ... array` → array reference null ở thao tác load/store.
- `Cannot invoke Integer.intValue` hoặc `Boolean.booleanValue` → unboxing một wrapper null.
- Nếu exception là `ArrayIndexOutOfBoundsException` → index, không phải reference null.

### Bước 4 — Truy ngược nguồn giá trị

Xem constructor, mapper, JSON deserializer, database nullable column, cache, Map.get, dependency response, collection element và các biến mutable. Đừng sửa riêng dòng throw nếu trạng thái không hợp lệ được tạo ở nơi khác.

### Bước 5 — Chọn xử lý theo contract

- Field bắt buộc → fail early với validation/`Objects.requireNonNull`.
- Field được phép vắng mặt → nhánh `null` rõ ràng/fallback hợp lệ.
- Array phải tồn tại → validate trước khi đọc length/index.
- Wrapper dùng như primitive → kiểm tra trước unboxing hoặc đổi kiểu nếu domain không có trạng thái null.
- Dữ liệu có thể bị thay đổi đồng thời → chỉnh model đồng bộ/immutability, không chỉ thêm null guard.

### Bước 6 — Viết regression test

Cho đúng input từng làm lỗi; assert exception type và behavior đúng. Nếu fix là từ chối input, assert **lỗi nghiệp vụ cụ thể**; nếu fix là fallback, assert giá trị đúng contract. Test thêm cả input bình thường để tránh một nhánh sửa lỗi làm thay đổi behavior hợp lệ.

### Bước 7 — Đối chiếu trước và sau

So sánh số lượng NPE, error rate, unit tests, integration tests và log từ bản mới. **Không coi việc stack trace biến mất là thành công** nếu code đã chuyển sang bỏ qua input thiếu hoặc tạo dữ liệu sai âm thầm.

## 15. Bảng test thực hành có kết quả kỳ vọng

| Case | Thiết lập | Expected behavior |
| --- | --- | --- |
| Đọc field | `Profile p=null; p.id` | `NullPointerException` |
| Ghi field | `Profile p=null; p.id=7` | `NullPointerException` |
| Field chain | `new Profile().address.city` | `NullPointerException` |
| Array length | `int[] a=null; a.length` | `NullPointerException` |
| Array read | `int[] a=null; a[0]` | `NullPointerException` |
| Array write | `int[] a=null; a[0]=9` | `NullPointerException` |
| Null array element | `new Profile[1][0]` là sai hướng: dùng `Profile[] a=new Profile[1]; a[0].id` | `NullPointerException` khi đọc `id` |
| Unbox local | `Integer n=null; int x=n` | `NullPointerException` |
| Unbox field | `new Profile().visits` sang `int` | `NullPointerException` |
| Unbox array | `Integer[] a={null}; int x=a[0]+1` | `NullPointerException` |
| Unbox Boolean | `Boolean b=null; if(b)...` | `NullPointerException` |
| Precondition | `Objects.requireNonNull(null, "required")` | `NullPointerException` với message do code đặt |
| Index ngoài mảng | `int[] a=new int[0]; a[0]` | `ArrayIndexOutOfBoundsException` |
| Null hợp lệ theo contract | `safeLength(null)` trong demo | `0` |
| Null visit hợp lệ theo contract | `safeVisits(null)` trong demo | `0` |
| Có address hợp lệ | `safeCity(valid)` | `Hue` |

Các ký hiệu `Profile`/`safeLength` là thành phần của chương trình mẫu mục 8. Với bài kiểm thử riêng, cần khai báo class/biến đầy đủ; đây là **test matrix**, không phải những đoạn Java hoàn chỉnh có thể paste cùng lúc.

## 16. Những lỗi xử lý NPE thường gặp

**1. “Field primitive không thể null, nên `profile.id` không gây NPE.”** Sai: receiver `profile` vẫn có thể null; NPE xảy ra trước khi lấy primitive field value.

**2. “Tạo mảng rồi thì phần tử không bao giờ null.”** Sai với mảng reference như `Profile[]`; những slot chưa gán mặc định null.

**3. “`a[0]` luôn NPE nếu lỗi.”** Sai: array null → NPE; array tồn tại nhưng index ngoài phạm vi → `ArrayIndexOutOfBoundsException`.

**4. “`Integer` được Java tự chuyển về 0 khi null.”** Sai: unboxing null ném NPE, không tự dùng default.

**5. “Không có call trong source thì không thể có invoke trong message.”** Sai: compiler sinh `Integer.intValue()`/`Boolean.booleanValue()` cho unboxing.

**6. “Đọc `profile.visits` gây NPE vì field null.”** Không hẳn: đọc field wrapper có thể **trả null thành công**; NPE nổ khi unbox/nhận vào primitive.

**7. “Thông báo helpful nêu tên biến nên đủ biết vì sao null.”** Sai: nó chỉ nêu **biểu thức null tại điểm lỗi**, không nói nguồn dữ liệu thiếu từ đâu.

**8. “`-g` là điều kiện bắt buộc để có helpful NPE.”** Sai: vẫn có thể nhận message từ bytecode dù thiếu local names; `-g` giúp hiển thị tên biến dễ hiểu hơn.

**9. “Helpful message luôn có giá trị và chữ ký cố định.”** Sai: `getMessage()` có thể null, wording khác theo VM và thông tin nội bộ.

**10. “`Objects.requireNonNull` được JVM tự phân tích như mọi field dereference.”** Sai: nó thường ném exception với **message do caller cung cấp**, một cơ chế khác.

**11. “Cứ catch NullPointerException rồi trả 0 là an toàn.”** Sai nếu dữ liệu thiếu là lỗi nghiêm trọng hoặc ảnh hưởng tiền, quyền truy cập và tính toàn vẹn dữ liệu.

**12. “`Boolean.TRUE.equals(b)` và `if(b)` tương đương cho mọi b.”** Sai khi `b==null`: cách thứ nhất false, cách thứ hai NPE; contract ba trạng thái cần xử lý riêng.

**13. “Map.getOrDefault luôn sửa null unboxing.”** Sai nếu key hiện diện với value null; default chỉ được dùng khi không có mapping.

**14. “Không còn NPE trong log nghĩa là root cause đã biến mất.”** Sai nếu chỉ bỏ qua null mà không đảm bảo nghiệp vụ; cần regression test.

**15. “Dùng Optional.get() là cách null-safe.”** Sai khi Optional rỗng: `get()` ném `NoSuchElementException`; cần `orElse`/`orElseThrow` hoặc check rõ.

**16. “Một null check đủ giải quyết concurrency.”** Sai khi object mutable thay đổi đồng thời; cần đảm bảo snapshot/visibility/synchronization phù hợp.

## 17. Bài tập có hướng dẫn đánh giá

### Bài A — Phân biệt field read và field write

Viết hai method độc lập: một gọi `p.id`, một thực hiện `p.id=100` với `p=null`. Dự đoán message `Cannot read field` và `Cannot assign field`. Bật `--details`, đối chiếu message **thực**, không khẳng định nguyên văn là contract.

### Bài B — Hai lớp null khác nhau trong array

Tạo:

```java
Profile[] first = null;
Profile[] second = new Profile[1];
```

Đây là snippet minh họa trong class có `Profile`. Thử:

- `first[0]`: array reference null, NPE ngay tại load phần tử.
- `second[0]`: trả null, **chưa NPE** nếu chỉ gán vào biến `Profile`.
- `second[0].id`: NPE khi đọc instance field từ element null.
- `second[1]`: index ngoài phạm vi → `ArrayIndexOutOfBoundsException`.

### Bài C — Unboxing ẩn trong điều kiện

Kiểm tra `Boolean approved = null` với `if (approved)` và `if (Boolean.TRUE.equals(approved))`. Nếu null là trạng thái “chưa duyệt”, thiết kế branch trả một trạng thái riêng thay vì hiểu nó là false.

### Bài D — Unboxing từ Map

Một `Map<String,Integer>` thiếu mapping của key `"x"`. So sánh kết quả của:

```java
int a = map.get("x");                  // NPE khi unbox null
Integer b = map.get("x");              // null, chưa NPE
int c = map.getOrDefault("x", 0);      // 0 nếu không có mapping
```

Đây là minh họa trong method có `map` khai báo sẵn. Bổ sung case **key tồn tại nhưng value null** để thấy `getOrDefault` không luôn đủ.

### Bài E — Đọc biểu thức null trong message

Biên dịch chương trình với `-g`; chạy `--details`. Phân loại từng message theo một trong ba nhóm: **field**, **array**, **unboxing**. Giải thích vì sao `nested-field` nêu `profile.address` và `unbox-field` nêu `profile.visits`.

### Bài F — Thiếu tên biến khi không biên dịch -g

Trên thư mục thử nghiệm riêng, biên dịch lại:

```bash
javac --release 17 -g:none NpeDiagnosticsDemo.java
java -XX:+ShowCodeDetailsInExceptionMessages NpeDiagnosticsDemo --details
```

So sánh cách JVM mô tả local variable với bản compile `-g`. Không đòi kết quả phải có chính xác `<localN>` trong mọi build; ghi **sự thay đổi thực tế**. Sau thử nghiệm có thể biên dịch lại `-g` để tiếp tục debugging.

### Bài G — Tắt helpful details

Chạy:

```bash
java -XX:-ShowCodeDetailsInExceptionMessages NpeDiagnosticsDemo --details
```

Quan sát các message NPE do VM tạo và message của `Objects.requireNonNull`. Giải thích vì sao **message do ứng dụng chỉ định** có thể vẫn tồn tại khi helpful bytecode analysis bị tắt.

### Bài H — Thiết kế bất biến dữ liệu

Chọn một DTO có `customer.address.city`, trong đó `address` là trường **bắt buộc**. Viết constructor hoặc boundary validation, sau đó test dữ liệu thiếu. Không cho hàm sâu trong business logic tự ý đổi city thành `"unknown"` nếu điều đó vi phạm contract.

### Bài I — Regression test mức hệ thống

Với một request bị NPE trong service, ghi lại nguyên nhân ở entity mapper/DB/JSON; viết test request bị thiếu field, xác định response lỗi phù hợp và giữ data integrity. Không so sánh exact JVM helpful message trong API test, vì đó không phải thông điệp do API của bạn cam kết.

**Tiêu chí đạt:** Người học tự tạo/đọc được ba nhóm NPE, phân biệt array receiver và element, nhận ra hidden unboxing, giải thích một thông báo helpful và sửa dựa trên contract; chương trình mục 8 trả đúng **16 dòng stdout cố định** khi chạy không có `--details`.

## 18. Tài liệu chính thức, hiện hành

- [OpenJDK JEP 358 — Helpful NullPointerExceptions](https://openjdk.org/jeps/358): tính năng bổ sung vào Java 14, mô tả bytecode analysis để xây thông báo NPE.
- [Oracle Java SE 17 — NullPointerException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NullPointerException.html): các trường hợp sử dụng null không hợp lệ, `getMessage()` và giới hạn thông báo chi tiết.
- [Oracle Java SE 26 — NullPointerException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/NullPointerException.html): xác nhận semantics vẫn áp dụng trong JDK hiện hành.
- [Oracle Java SE 17 — java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-XX:+ShowCodeDetailsInExceptionMessages` và giá trị mặc định trong HotSpot.
- [Oracle JDK 15 Release Notes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): thay đổi mặc định bật `ShowCodeDetailsInExceptionMessages` từ JDK 15.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-g`, `-g:vars` và thông tin debug.
- [Java Language Specification 17 — `5.1.8 Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8): chuyển wrapper sang primitive và NPE khi wrapper null.
- [Java Language Specification 17 — `15.10 Array Access Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10): cách đánh giá access mảng, null receiver và chỉ số.
- [Java Language Specification 17 — `15.11 Field Access Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.11): hành vi access field ở Java.
- [Oracle Java SE 17 — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `requireNonNull`, `equals`, `checkIndex` và các phương tiện kiểm tra input.

**Ghi nhớ:** Khi thấy NPE, đừng chỉ tìm chữ `null` trong cả dòng code. Hãy xác định **thao tác JVM đang thực hiện**: đọc/ghi **field**, đọc/ghi/lấy length của **array**, hay **unboxing** một wrapper. Helpful NPE giúp chỉ ra biểu thức null; còn **nguyên nhân vì sao dữ liệu null xuất hiện** phải được truy ngược từ validation, constructor, mapping, database, API contract hoặc concurrency. Bắt đầu bằng **loại exception + stack trace + message**, sửa theo **hợp đồng dữ liệu**, rồi bảo vệ bằng **regression test**.