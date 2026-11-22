# ResourceBundle.getString, getObject, getStringArray và kiểu tài nguyên

## 1. Vấn đề cần giải quyết

Một ứng dụng đa ngôn ngữ không chỉ phải tìm đúng tài nguyên theo `Locale` mà còn phải **đọc dữ liệu đúng kiểu**. Ví dụ, một màn hình có thể cần:

- Một câu thông báo: `"Xin chào"` — giá trị kiểu `String`.
- Nhiều nhãn menu: `["Mở", "Lưu"]` — giá trị kiểu `String[]`.
- Một tham số cấu hình của giao diện: `3` — giá trị kiểu `Integer`.
- Một đối tượng khác do ứng dụng định nghĩa, nếu thực sự có lý do sử dụng nó như tài nguyên.

Java cung cấp ba phương thức của `java.util.ResourceBundle`:

```java
String getString(String key);
String[] getStringArray(String key);
Object getObject(String key);
```

Cả ba đều tìm theo **khóa `String`** trong bundle hiện tại và hệ thống **parent bundle**. Sự khác nhau quan trọng là kiểu kết quả và khả năng xảy ra lỗi ép kiểu.

Bài học này giải thích các kiểu tài nguyên, cách lấy dữ liệu bằng từng phương thức, sự khác nhau giữa `PropertyResourceBundle` và `ListResourceBundle`, cơ chế fallback theo key, ngoại lệ, cũng như cách thiết kế ví dụ chạy được với Java 17+.

## 2. ResourceBundle lưu gì và được tìm như thế nào?

`ResourceBundle` là lớp trừu tượng đại diện cho tập cặp `key → value` được chọn theo một tên gốc (base name) và một `Locale`. Một gia đình bundle có thể có các thành viên như:

```text
Messages          ← bundle gốc
Messages_vi       ← bản tiếng Việt
Messages_en       ← bản tiếng Anh
Messages_en_US    ← bản tiếng Anh ở Mỹ
```

Một lệnh tải điển hình:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);
```

Trong ví dụ này Java tìm bundle thích hợp theo candidate locales của `vi-VN`, có thể chọn `Messages_vi` khi không có `Messages_vi_VN`. Nếu một key thiếu trong bundle tiếng Việt, lời gọi đọc tài nguyên có thể tìm ở **parent** như `Messages`. Đây là một phần của cơ chế fallback để tránh phải lặp lại mọi key ở từng bản địa hóa.

Phân biệt hai việc:

1. **Chọn bundle** bằng `ResourceBundle.getBundle(baseName, locale)`: có chiến lược ứng viên, default locale và base bundle. Việc ứng viên nào được chọn phụ thuộc bundle hiện có, `Control`/provider và môi trường.
2. **Tìm key** bằng `getString`, `getStringArray` hoặc `getObject` trên bundle đã chọn: thử bundle hiện tại, rồi parent cho đến khi tìm được giá trị.

Không nên hiểu “thiếu bản dịch” là luôn trả về chuỗi rỗng, `null` hay tiếng Anh. Nếu **không có bundle** phù hợp, `getBundle` có thể ném `MissingResourceException`; nếu **không có key** trong chuỗi bundle/parent, các getter cũng ném `MissingResourceException`.

### Key và value khác nhau

- **Key** bắt buộc là `String` và phân biệt chữ hoa/thường: `"welcome"` khác `"Welcome"`.
- **Value** trong một `ResourceBundle` nói chung có thể là một `Object`; **kiểu giá trị thực tế** phụ thuộc định dạng bundle và cách tạo bundle.
- Ba getter là phương thức của `ResourceBundle`; chúng **không tự chuyển đổi** số thành chuỗi, chuỗi CSV thành mảng hay đối tượng thành bản dịch.

## 3. So sánh ba phương thức

| Phương thức | Kiểu trả về | Thích hợp khi | Điều cần nhớ |
| --- | --- | --- | --- |
| `getString("key")` | `String` | Thông điệp, tiêu đề, nhãn, pattern cho formatter | Giá trị thực phải là `String` |
| `getStringArray("key")` | `String[]` | Một tài nguyên thực sự là mảng chuỗi | Giá trị thực phải là **`String[]`**, không phải chuỗi có dấu phẩy |
| `getObject("key")` | `Object` | Giá trị có kiểu khác `String`/`String[]` hoặc cần xử lý động | Người gọi phải kiểm tra/ép về kiểu thích hợp |

Về bản chất, hai phương thức chuyên biệt tương đương ý tưởng ép kiểu:

```java
String text = (String) bundle.getObject("welcome");
String[] menu = (String[]) bundle.getObject("menu");
```

Do đó:

- `getString("welcome")` thành công nếu giá trị thực là `String`.
- `getStringArray("menu")` thành công nếu giá trị thực là `String[]`.
- `getObject("menu")` vẫn trả về một `Object` mà kiểu runtime là `String[]`.
- `getString("maxAttempts")` không tự gọi `toString()` cho số nguyên; nó ném `ClassCastException`.
- `getStringArray("menu")` không phân tích `"Home,Settings"` hoặc `"Mở|Lưu"`; chuỗi đó vẫn là `String` và phép cast sang `String[]` thất bại.

Hai phương thức `getString` và `getStringArray` đều là `final` trên `ResourceBundle`. Khi phát triển bundle tùy chỉnh, bạn triển khai cách truy xuất dữ liệu qua API chuyên dụng của lớp con (ví dụ `getContents` của `ListResourceBundle`), không ghi đè getter này.

## 4. Kiểu tài nguyên phụ thuộc nguồn bundle

### 4.1. PropertyResourceBundle: mỗi giá trị là String

Với bundle dạng file `.properties`, chẳng hạn **`messages_vi.properties`**:

```properties
welcome=Xin chào
button.save=Lưu
button.cancel=Hủy
menu=Mở,Lưu
maxAttempts=3
```

`PropertyResourceBundle` tải các giá trị này thành **`String`**:

| Key | Kiểu Java khi đọc | Giá trị |
| --- | --- | --- |
| `welcome` | `String` | `"Xin chào"` |
| `button.save` | `String` | `"Lưu"` |
| `menu` | `String` | `"Mở,Lưu"`, vẫn là một chuỗi |
| `maxAttempts` | `String` | `"3"`, không phải `Integer` |

Ví dụ:

```java
ResourceBundle b = ResourceBundle.getBundle(
        "messages", Locale.forLanguageTag("vi"));

String welcome = b.getString("welcome");
String menu = b.getString("menu");
String attempts = b.getString("maxAttempts");
int number = Integer.parseInt(attempts);
```

Đoạn trên là **snippet**; cần `import java.util.Locale;` và `import java.util.ResourceBundle;` cùng file properties đặt trên classpath. `Integer.parseInt` là **bước chuyển kiểu tường minh của ứng dụng** và có thể ném `NumberFormatException` nếu dữ liệu không phải số nguyên hợp lệ.

**Không gọi `b.getStringArray("menu")` trong trường hợp này**: vì `"Mở,Lưu"` là một `String`, lời gọi sẽ ném `ClassCastException`. Nếu muốn tập nhãn từ properties, thường nên lưu thành **nhiều key độc lập** (`menu.open`, `menu.save`) để mỗi chuỗi được dịch đúng ngữ cảnh. Dùng `split(",")` chỉ khi ứng dụng thực sự định nghĩa một định dạng dữ liệu phân tách với quy tắc escape, dấu phẩy trong nội dung và kiểm tra dữ liệu rõ ràng.

Trong Java 9+, `ResourceBundle` có thể đọc properties với UTF-8 và cơ chế tương thích; cần bảo đảm encoding thống nhất giữa tệp và công cụ build. Đối với ví dụ Java 17+, hãy lưu file UTF-8.

### 4.2. ListResourceBundle: value có thể là Object

`ListResourceBundle` là lớp con của `ResourceBundle`. Mỗi lớp bundle cung cấp các cặp `Object[][]` thông qua `protected Object[][] getContents()`. Key vẫn phải là `String`, còn value có thể là:

```java
{"welcome", "Welcome"}               // String
{"menu", new String[] {"Open", "Save"}}  // String[]
{"maxAttempts", Integer.valueOf(3)}    // Integer
```

Không phải mọi object đều hợp lý để bản địa hóa. Phần lớn thông điệp UI chỉ cần `String`; `String[]` có ích cho một tập lựa chọn thực sự thuộc cùng tài nguyên; object có cấu trúc chỉ phù hợp khi nhà phát triển kiểm soát cả định nghĩa, kiểu dữ liệu và vòng đời.

**Một số điểm thiết kế:**

- Giá trị trong `ListResourceBundle` có thể là `String[]` thật, do đó `getStringArray` có cơ sở để hoạt động.
- Chọn đúng getter theo **kiểu runtime**, không theo tên key. Key `"count"` không biến giá trị thành số.
- Không nên trả object mutable rồi sửa nó từ nhiều luồng. `ResourceBundle` được dùng lại/cached; một mảng hoặc object nhận từ `getObject` có thể được chia sẻ. Nếu cần sửa mảng, hãy sao chép: `bundle.getStringArray("menu").clone()`.
- Nếu một bản dịch dùng `String` còn một bản khác dùng `String[]` cho **cùng key**, code sẽ chỉ hoạt động với một số locale. Giữ một **hợp đồng kiểu thống nhất** xuyên suốt các bundle trong cùng gia đình.

### 4.3. Các nguồn tài nguyên mở rộng

`ResourceBundle` còn có thể được cài đặt bằng subclass/provider tùy chỉnh. `getObject` vẫn có kiểu trả về `Object`; kết quả thực tế tùy implementation. Không giả định giá trị có thể tự chuyển đổi sang dạng mong muốn. `PropertyResourceBundle`, `ListResourceBundle` và các bộ nạp riêng nên được dùng theo một quy ước có tài liệu và kiểm thử.

## 5. Ví dụ Java 17+ chạy được: String, String[] và Integer

Tạo ba file Java **cùng một thư mục**, trong **default package** (không có dòng `package`). Không cần file `.properties` trong ví dụ này.

**Tệp `Messages.java`** — tài nguyên mặc định:

```java
import java.util.ListResourceBundle;

public class Messages extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"welcome", "Welcome"},
                {"menu", new String[] {"Open", "Save"}},
                {"maxAttempts", Integer.valueOf(3)}
        };
    }
}
```

**Tệp `Messages_vi.java`** — bản tiếng Việt chỉ ghi đè hai key:

```java
import java.util.ListResourceBundle;

public class Messages_vi extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"welcome", "Xin chào"},
                {"menu", new String[] {"Mở", "Lưu"}}
        };
    }
}
```

**Tệp `BundleTypesDemo.java`** — đọc các kiểu tài nguyên và ngoại lệ:

```java
import java.util.Arrays;
import java.util.Locale;
import java.util.MissingResourceException;
import java.util.ResourceBundle;

public class BundleTypesDemo {
    public static void main(String[] args) {
        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", Locale.forLanguageTag("vi-VN"));

        String welcome = bundle.getString("welcome");
        String[] menu = bundle.getStringArray("menu");
        Object rawMenu = bundle.getObject("menu");
        Object rawLimit = bundle.getObject("maxAttempts");

        System.out.println("Bundle locale: " + bundle.getLocale().toLanguageTag());
        System.out.println("getString: " + welcome);
        System.out.println("getStringArray: " + Arrays.toString(menu));
        System.out.println("getObject menu is String[]: " + (rawMenu instanceof String[]));
        System.out.println("getObject maxAttempts: " + rawLimit);
        System.out.println("maxAttempts type: " + rawLimit.getClass().getSimpleName());
        System.out.println("parent key exists: " + bundle.containsKey("maxAttempts"));

        try {
            bundle.getString("maxAttempts"); // Integer, không phải String
        } catch (ClassCastException e) {
            System.out.println("wrong getString: " + e.getClass().getSimpleName());
        }

        try {
            bundle.getStringArray("welcome"); // String, không phải String[]
        } catch (ClassCastException e) {
            System.out.println("wrong getStringArray: " + e.getClass().getSimpleName());
        }

        try {
            bundle.getObject("does.not.exist");
        } catch (MissingResourceException e) {
            System.out.println("missing key: " + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 Messages.java Messages_vi.java BundleTypesDemo.java
java BundleTypesDemo
```

**Stdout kỳ vọng:**

```text
Bundle locale: vi
getString: Xin chào
getStringArray: [Mở, Lưu]
getObject menu is String[]: true
getObject maxAttempts: 3
maxAttempts type: Integer
parent key exists: true
wrong getString: ClassCastException
wrong getStringArray: ClassCastException
missing key: MissingResourceException
```

Giải thích:

1. `getBundle("Messages", vi-VN)` không có lớp `Messages_vi_VN`, nên lấy `Messages_vi`; `getLocale()` của bundle được chọn là `vi`.
2. `getString("welcome")` đọc chuỗi tiếng Việt từ `Messages_vi`.
3. `getStringArray("menu")` trả về mảng `String[]` mà lớp `Messages_vi` định nghĩa. `Arrays.toString` chỉ dùng để hiển thị mảng dễ đọc.
4. `getObject("menu")` trả về object có kiểu runtime `String[]`; từ khóa `instanceof` cho kết quả `true`.
5. `Messages_vi` không có key `maxAttempts`, nên lời gọi `getObject("maxAttempts")` tra cứu parent `Messages` và nhận `Integer(3)`. `containsKey` cũng xét cả cha.
6. Hai lời gọi dùng **getter sai kiểu** ném `ClassCastException`, trong khi key không tìm thấy ném `MissingResourceException`. Các ngoại lệ được bắt chỉ để minh họa, không được lờ đi tất cả lỗi này trong ứng dụng thật.

**Lưu ý khi chạy:** ba lớp công khai phải được lưu đúng tên tệp và cùng classpath. Tránh có sẵn `Messages.properties` hoặc `Messages_vi.properties` cùng tên trong thư mục vì chúng có thể làm khó việc giải thích bundle nào được chọn nếu môi trường không giống ví dụ. Các tệp đều dùng UTF-8 để chữ tiếng Việt hiển thị đúng; console phải dùng mã hóa phù hợp.

## 6. Các ngoại lệ và cách xử lý đúng

| Tình huống | Ngoại lệ/kết quả | Lý do |
| --- | --- | --- |
| `getString("unknown")`, không có key tại bundle hay parent | `MissingResourceException` | Không tìm thấy key |
| `getObject("unknown")`, không có key tại bundle hay parent | `MissingResourceException` | `getObject` không trả `null` khi không tìm ra key |
| `getStringArray("unknown")` | `MissingResourceException` | Thiếu key, trước khi kiểm tra kiểu |
| `getString("maxAttempts")` khi value là `Integer` | `ClassCastException` | Không thể ép thành `String` |
| `getStringArray("welcome")` khi value là `String` | `ClassCastException` | Không thể ép thành `String[]` |
| `getStringArray("menu")` khi value là `Object[]` chứa các chuỗi | `ClassCastException` | Kiểu mảng runtime là `Object[]`, không phải `String[]` |
| `getString(null)`, `getObject(null)` hoặc `getStringArray(null)` | `NullPointerException` | Key không được `null` |
| `getBundle("missingFamily", locale)` mà không có bundle hợp lệ | `MissingResourceException` | Chưa có một bundle nào để đọc key |

**Đừng bắt `ClassCastException` để trả một thông điệp rỗng rồi che đi lỗi tài nguyên.** Với bundle do ứng dụng sở hữu, đây thường là lỗi cấu hình hoặc hợp đồng kiểu bị phá vỡ, nên cần phát hiện sớm trong kiểm thử và ghi log có tên base bundle, key, locale và kiểu mong đợi.

Với một key **tùy chọn thật sự**, có thể kiểm tra `containsKey` trước, sau đó xử lý default do ứng dụng định nghĩa. Nhưng `containsKey` không kiểm tra kiểu; cùng một key có thể tồn tại nhưng mang kiểu sai.

Ví dụ khi chỉ dùng `getObject` và không kiểm soát kiểu value:

```java
Object item = bundle.getObject("menu");

if (item instanceof String[] items) {
    for (String label : items) {
        System.out.println(label);
    }
} else {
    throw new IllegalStateException("Resource menu must be String[]");
}
```

Đoạn này là **snippet** dùng biến `bundle` đã tạo từ trước; `instanceof String[] items` là pattern matching có trong Java 17. Không ép kiểu từ `Object` mà chưa kiểm tra khi dữ liệu có thể được thay thế bởi provider khác.

## 7. Kiểu tài nguyên: lỗi thường xảy ra khi chuyển từ .properties sang Java

Hãy so sánh hai giá trị tưởng giống nhau:

**Trong `labels.properties`:**

```properties
choices=Yes,No
```

**Trong `ListResourceBundle`:**

```java
{"choices", new String[] {"Yes", "No"}}
```

Cả hai có thể được hiển thị như “Yes,No”, nhưng kiểu Java hoàn toàn khác nhau:

| Nguồn | `getObject("choices")` | `getString("choices")` | `getStringArray("choices")` |
| --- | --- | --- | --- |
| `PropertyResourceBundle` | `String` | Thành công | `ClassCastException` |
| `ListResourceBundle` có `new String[]` | `String[]` | `ClassCastException` | Thành công |
| `ListResourceBundle` có `new Object[] {"Yes", "No"}` | `Object[]` | `ClassCastException` | `ClassCastException` |

Vì vậy, **đổi hình thức lưu tài nguyên** từ file properties sang Java class có thể vô tình đổi hợp đồng kiểu. Khi refactor, cần kiểm thử các key và getter mà các caller đang dùng. Không suy ra kiểu từ cách một giá trị được in ra màn hình.

Nếu chỉ cần hiển thị hai nhãn độc lập, thiết kế thường rõ ràng hơn là:

```properties
choice.yes=Yes
choice.no=No
```

Sau đó gọi `getString("choice.yes")` và `getString("choice.no")`. Đối với danh sách dài có nội dung thay đổi giữa các locale, cân nhắc liệu thứ tự, số lượng mục và ID của lựa chọn có thuộc nghiệp vụ hay không; việc lấy các nhãn hiển thị từ bản dịch phải giữ nguyên **định danh nghiệp vụ** khi người dùng chọn một mục.

## 8. Fallback cho key không đồng nghĩa với fallback khi sai kiểu

Giả sử parent `Messages` chứa:

```java
{"retryLabel", "Retry"}
```

Còn bản `Messages_vi` chứa:

```java
{"retryLabel", new String[] {"Thử lại"}}
```

Lời gọi `bundle.getString("retryLabel")` trên bản tiếng Việt sẽ tìm thấy key ở bundle con, rồi **ép kiểu giá trị con** thành `String`. Vì key đã có giá trị, phương thức **không tự bỏ qua nó để dùng `"Retry"` của parent**. Kết quả là `ClassCastException`. Fallback theo key giải quyết **key vắng mặt**, không giải quyết **value sai kiểu**.

Do đó, cách quản lý hợp đồng giữa các ngôn ngữ là:

1. Với một key, xác định **kiểu giá trị thống nhất** cho toàn bộ locale.
2. Dùng quy ước tên rõ nghĩa, ví dụ `message.login.success` (chuỗi) và `navigation.labels` (mảng nếu thực sự cần).
3. Viết kiểm thử truy cập tất cả key thiết yếu trong từng locale hỗ trợ, thay vì chỉ kiểm tra bundle tải được.
4. Nếu cho phép key thiếu, xác định rõ nó được kế thừa từ parent nào và kiểm tra tiếng nói/câu chữ sau fallback có còn phù hợp ngữ cảnh hay không.
5. Khi cần một bộ tài nguyên mạnh về kiểu, cân nhắc wrapper với phương thức như `requireText(key)` và `requireTextArray(key)` để thông báo lỗi kèm tên key và locale.

Lưu ý `getObject` là `final` trên `ResourceBundle` và thực hiện tra cứu qua `handleGetObject` của các lớp con, rồi parent nếu cần. Nó không tự sửa lỗi kiểu và không có cơ chế tự động ép từ `Integer` sang `String`.

## 9. ResourceBundle và cách tách dữ liệu khỏi ứng dụng

Trong ứng dụng lớn, nên chọn loại tài nguyên theo mục đích:

- **Thông điệp giao diện:** dùng `String` và `getString`; nếu có biến động `{0}`, `{1}`, xử lý thêm bằng `MessageFormat` với locale tương ứng. Không ghép từng đoạn thông điệp theo thứ tự tiếng Anh.
- **Nhóm nhãn cố định:** có thể dùng `String[]` và `getStringArray` trong `ListResourceBundle`, nhưng phải giữ thứ tự/kiểu trên mọi locale; thường nhiều key có tên rõ nghĩa dễ bảo trì hơn.
- **Dữ liệu có cấu trúc hoặc cấu hình nghiệp vụ:** nên đặt ở hệ thống cấu hình/schema phù hợp nếu không thực sự là nội dung bản địa hóa. `getObject` có thể đọc object nhưng không tự kiểm tra schema và không thay thế cơ chế kiểm tra hợp lệ.
- **Quy tắc quốc tế hóa tiêu chuẩn:** ngày, số, tiền tệ nên đi qua formatter chuyên dụng (`DateTimeFormatter`, `NumberFormat`), không hardcode các quy tắc format tùy vùng trong bundle.

Không đặt tham chiếu đến dữ liệu nhạy cảm, token hoặc secret trong tài nguyên dịch. Giá trị tài nguyên có thể được đóng gói, kiểm tra hoặc phục vụ tại nhiều nơi; quyền truy cập vào chuỗi dịch không phải biện pháp bảo vệ bí mật.

### Vấn đề hiệu năng và vòng đời

`ResourceBundle.getBundle` có cơ chế cache. Không cần tải lại theo từng key; lấy bundle theo locale rồi tái sử dụng trong phạm vi xử lý phù hợp. Với `ListResourceBundle`, object/mảng được lưu trong bundle có thể được chia sẻ. `getStringArray` không hứa tạo mảng mới cho mỗi lời gọi; không sửa nội dung mảng được trả về trừ khi đã sao chép. Nếu có cập nhật nóng tài nguyên trong thời gian chạy, đó là bài toán vòng đời/cache riêng, không thể giải quyết bằng việc đổi `getString` sang `getObject`.

Đừng gọi `Locale.setDefault(...)` theo từng request để lựa chọn bundle. Trong dịch vụ nhiều luồng, nên truyền `Locale` của request đến `getBundle` và formatter; thay đổi default JVM có thể ảnh hưởng xử lý đồng thời.

## 10. Checklist kiểm thử

Kiểm thử theo nhiều locale và nhiều loại nguồn, đặc biệt khi di chuyển từ `.properties` sang `ListResourceBundle`:

| Kiểm tra | Kết quả cần đúng |
| --- | --- |
| Key kiểu `String` trong locale cụ thể | `getString` trả đúng nội dung đã dịch |
| Key kiểu `String[]` | `getStringArray` giữ đúng số phần tử và thứ tự |
| Key kiểu `Integer` hoặc object khác | `getObject` trả kiểu runtime mong đợi; caller ép kiểu an toàn |
| Key chỉ tồn tại ở bundle gốc | Có thể truy cập qua parent; kết quả vẫn đúng kiểu |
| Key có ở bundle con nhưng sai kiểu | `ClassCastException`, không âm thầm fallback sang parent |
| Key vắng mặt hoàn toàn | `MissingResourceException`, xử lý theo chính sách của sản phẩm |
| Key là `null` | `NullPointerException` |
| File `.properties` chứa `"a,b"` | Vẫn là `String`, không phải `String[]` |
| Hai locale khai báo cùng key khác kiểu | Phát hiện bằng test hợp đồng tài nguyên |
| Bundle chứa mảng/object mutable | Người dùng API không sửa trạng thái dùng chung |
| Resource file dùng tiếng Việt | Dấu Unicode hiển thị chính xác, không bị lỗi encoding |
| Bản dịch fallback từ parent | Câu chữ sau fallback vẫn phù hợp ngôn ngữ và ngữ cảnh |

Cần phân biệt kiểm thử API với kiểm thử nội dung: một bundle có đủ key và đúng kiểu vẫn có thể chứa văn bản sai ngữ cảnh, sai số nhiều hoặc cách dịch khó hiểu. Các lỗi đó phải được kiểm tra bằng review ngôn ngữ và UI thực tế.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `getString("count")` có trả về `"3"` nếu value của key `count` trong `ListResourceBundle` là `Integer.valueOf(3)` không?

**Đáp án:** Không. `getString` cần giá trị `String`; số nguyên sẽ gây `ClassCastException`. Muốn định dạng con số hãy lấy bằng `getObject`, kiểm tra kiểu và format theo yêu cầu.

**Câu 2.** File `messages.properties` có dòng `colors=red,green,blue`. Gọi `getStringArray("colors")` sẽ trả ba phần tử?

**Đáp án:** Không. `PropertyResourceBundle` đọc giá trị thành một `String`. `getStringArray` yêu cầu runtime type `String[]` nên ném `ClassCastException`.

**Câu 3.** Vì sao bản dịch tiếng Việt có thể đọc key `maxAttempts` chỉ khai báo ở bundle gốc?

**Đáp án:** Khi tìm key ở bundle con không thành công, `ResourceBundle.getObject` truy vấn parent. Cả `getString` và `getStringArray` cũng hưởng cơ chế đó vì chúng đọc dữ liệu thông qua `getObject`.

**Câu 4.** Parent có `String` cho một key, bundle con chứa cùng key nhưng lại khai báo `String[]`. `getString` có tự chuyển lên parent không?

**Đáp án:** Không. Key đã tồn tại tại bundle con; phép ép kiểu thất bại với `ClassCastException`. Chỉ key vắng mặt mới dẫn đến tìm parent.

**Câu 5.** Khi một key không tồn tại ở cả bundle và parent, `getObject` trả gì?

**Đáp án:** Ném `MissingResourceException`, không trả `null`.

**Câu 6.** Nếu cần chỉnh sửa danh sách nhãn lấy từ `getStringArray`, làm thế nào an toàn?

**Đáp án:** Sao chép trước bằng `clone()` hoặc `Arrays.copyOf(...)`; tránh thay đổi trực tiếp mảng do bundle giữ vì nó có thể được cache và dùng chung.

## 12. Ghi nhớ

- `getString` lấy **String**, `getStringArray` lấy **String[]**, `getObject` lấy **Object**. Chọn getter theo **kiểu value thực tế**.
- `PropertyResourceBundle` thông thường lưu mọi value dưới dạng chuỗi; `ListResourceBundle` cho phép cung cấp mảng và các object Java.
- **Thiếu key** gây `MissingResourceException`, **sai kiểu** gây `ClassCastException`, và **key null** gây `NullPointerException`.
- Parent bundle hỗ trợ fallback khi **không có key**, không giải quyết key đã tồn tại với kiểu sai.
- Hợp đồng kiểu phải nhất quán giữa các locale; kiểm thử fallback, kiểu dữ liệu, Unicode và trường hợp thiếu key trước khi phát hành.

Tài liệu tham khảo chính thức:

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Java SE 21 — ListResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ListResourceBundle.html)
