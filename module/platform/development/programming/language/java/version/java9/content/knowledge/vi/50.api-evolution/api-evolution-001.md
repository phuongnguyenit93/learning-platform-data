# Metadata `since` và `forRemoval` của `@Deprecated` trong tiến hóa API (Java 9+)

## 1. Khái niệm và mục tiêu

Khi một thư viện Java phát triển, tác giả có thể thay thế một API cũ bằng API mới rõ ràng, an toàn hoặc dễ bảo trì hơn. Không phải lúc nào cũng có thể xóa API cũ ngay lập tức: ứng dụng khách có thể đang dùng nó, còn thư viện cần duy trì khả năng tương thích trong thời gian chuyển đổi.

`java.lang.Deprecated` là annotation chuẩn báo cho nhà phát triển, compiler, IDE và công cụ tài liệu biết một phần tử **không còn được khuyến nghị sử dụng**. Annotation `@Deprecated` có từ Java 5; **Java 9 bổ sung hai phần tử metadata**:

- `String since()`: phiên bản **đầu tiên phần tử bị deprecated**, không phải phiên bản nó xuất hiện.
- `boolean forRemoval()`: `true` khi phần tử được **dự định loại bỏ trong một phiên bản tương lai**; `false` nếu chưa công bố ý định loại bỏ cụ thể tại thời điểm đánh dấu.

Hai phần tử này **vẫn được hỗ trợ trong Java SE hiện hành** (Java 17+ và Java SE 26), hoàn toàn phù hợp để thiết kế quá trình tiến hóa API hiện nay.

Ví dụ cú pháp:

```java
/**
 * Phương thức cũ.
 * @deprecated Từ 2.1, hãy chuyển sang API thay thế đã công bố.
 */
@Deprecated(since = "2.1", forRemoval = false)
public void oldOperation() {
    // Giữ lại tạm thời cho mã đang cần tương thích.
}
```

Đây là **phương thức minh họa trong một lớp**, không phải file độc lập. Bài học hướng tới cách **đánh dấu, hiểu cảnh báo và di chuyển khỏi API deprecated**, chứ không khuyên dùng các phương thức cũ trong ứng dụng mới.

## 2. Contract chính xác của hai metadata

| Phần tử của `@Deprecated` | Kiểu | Giá trị mặc định | Nội dung biểu đạt |
| --- | --- | --- | --- |
| `since()` | `String` | `""` | Chuỗi phiên bản đầu tiên mà API bắt đầu bị deprecated. |
| `forRemoval()` | `boolean` | `false` | `true` nếu có ý định bỏ API trong tương lai; `false` nếu chưa có ý định bỏ cụ thể. |

Các giá trị mặc định thể hiện khi không khai báo:

```java
@Deprecated
public void first() { }

@Deprecated(since = "2.1")
public void second() { }

@Deprecated(since = "3.0", forRemoval = true)
public void third() { }
```

Đây là **fragment các phương thức bên trong một lớp**. Phân tích:

- `first`: `since() == ""`, `forRemoval() == false`.
- `second`: `since() == "2.1"`, `forRemoval() == false` (mặc định).
- `third`: `since() == "3.0"`, `forRemoval() == true`.

`since` là một **chuỗi thông tin phiên bản**, không phải một số nguyên được so sánh tự động với version của JDK hoặc library. Đối với **thư viện do bạn phát hành**, hãy dùng hệ phiên bản của thư viện (ví dụ `"2.1"`, `"3.0"`). Đối với API của JDK, giá trị thường biểu diễn phiên bản Java tương ứng. Không suy ra một deadline từ chuỗi này.

### 2.1. `since` không đồng nghĩa với `@since` của Javadoc

Giả sử phương thức được giới thiệu ở phiên bản thư viện **1.0**, nhưng chỉ bị deprecated ở **2.1**:

```java
/**
 * Định dạng chuỗi theo quy tắc từng được hỗ trợ từ 1.0.
 *
 * @param text văn bản đầu vào
 * @return văn bản được xử lý
 * @since 1.0
 * @deprecated Từ 2.1, dùng API chuẩn hóa mới.
 */
@Deprecated(since = "2.1")
public String oldFormat(String text) {
    return text.trim();
}
```

`@since 1.0` (thẻ Javadoc) là **phiên bản xuất hiện đầu tiên**. `@Deprecated(since = "2.1")` (thuộc tính annotation) là **phiên bản đầu tiên bị deprecated**. Khác nhau là đúng, không phải mâu thuẫn.

**Lưu ý:** một số API có `since() == ""` vì tác giả không khai báo metadata. Giá trị này **không** có nghĩa “deprecated từ Java 9”; nó chỉ có nghĩa **không biết phiên bản từ annotation**. Java API khuyến nghị cung cấp `since` cho phần tử mới bị deprecated.

### 2.2. `forRemoval=false`: deprecated thông thường

`forRemoval=false` (mặc định) diễn đạt: API đã không còn được khuyến nghị, nhưng khi đánh dấu chưa có ý định loại bỏ cụ thể. JLS gọi đây là **ordinarily deprecated**. Hệ quả:

- Code khách **nên chuyển** sang API được hướng dẫn trong Javadoc.
- Library có thể giữ API cũ để tương thích trong một thời gian dài.
- **Không** được diễn giải là tác giả cam kết giữ API mãi mãi. Chính sách có thể đổi và thông báo loại bỏ sau này.

### 2.3. `forRemoval=true`: terminally deprecated

`forRemoval=true` báo API **được dự định xóa trong một phiên bản tương lai**; JLS gọi đây là **terminally deprecated**. Compiler có nhóm cảnh báo `[removal]` riêng để thể hiện mức rủi ro cao hơn.

**Quan trọng:** đây là thông báo *ý định*, không phải lệnh làm compiler/JVM tự động xóa API vào bản kế tiếp. Thời điểm xóa thực tế phụ thuộc release notes, chính sách tương thích, kế hoạch của library và quá trình đánh giá ảnh hưởng. Cần **đối chiếu phiên bản và tài liệu chính thức**, không đoán lịch xóa từ `true`.

### 2.4. Ma trận cách đọc

| `since` | `forRemoval` | Diễn giải | Hành động |
| --- | --- | --- | --- |
| `""` | `false` | Đã deprecated; không khai báo mốc từ khi nào. | Tìm API thay thế và kiểm tra tài liệu. |
| `"2.1"` | `false` | Deprecated từ thư viện 2.1; chưa công bố ý định bỏ cụ thể. | Lập kế hoạch migration. |
| `"3.0"` | `true` | Deprecated từ thư viện 3.0 và có ý định xóa. | Ưu tiên migration, xem release notes. |
| `""` | `true` | Có ý định xóa nhưng không khai báo version bắt đầu deprecated. | Thêm thông tin ở Javadoc/changelog nếu bạn quản lý API. |

## 3. Cú pháp annotation và thẻ Javadoc: dùng cùng nhau

Ba cú pháp khác nhau dễ bị nhầm:

| Cú pháp | Vị trí | Tác dụng |
| --- | --- | --- |
| `@Deprecated(since="...", forRemoval=true)` | Trước khai báo method/type/field... | Metadata cho compiler, tooling, reflection. |
| `@deprecated Lý do và API thay thế` | Trong chú thích `/** ... */` | Văn bản giải thích cho người đọc Javadoc. |
| `@since Phiên bản` | Trong `/** ... */` | Mốc **API được giới thiệu**, không phải mốc deprecated. |

Ví dụ khi thư viện công bố API mới:

```java
/**
 * Chuẩn hóa mã đầu vào.
 *
 * @param input giá trị đầu vào
 * @return dữ liệu đã chuẩn hóa
 */
public static String normalize(String input) {
    return input.trim();
}

/**
 * Chuẩn hóa mã theo hợp đồng cũ.
 *
 * @param input giá trị đầu vào
 * @return dữ liệu đã chuẩn hóa
 * @since 1.0
 * @deprecated Từ 2.1, dùng {@link #normalize(String)}.
 *             API mới có hợp đồng rõ ràng hơn.
 */
@Deprecated(since = "2.1", forRemoval = false)
public static String legacyNormalize(String input) {
    return normalize(input);
}
```

Đây là **fragment trong một lớp**, không phải file độc lập. Annotation làm compiler nhận biết trạng thái, còn Javadoc giải thích *vì sao* và *di chuyển đi đâu*. Tài liệu chính thức khuyến nghị **luôn đặt cả `@Deprecated` và tag `@deprecated`**, không chỉ một trong hai. Nếu dùng tag Javadoc mà thiếu annotation, bật `javac -Xlint:dep-ann` có thể phát hiện.

Nếu API thay thế thay đổi về nullability, kiểu trả về, side effect, encoding, timeout hoặc exception, ghi rõ những khác biệt này trong Javadoc/migration guide. Metadata `since` và `forRemoval` không thể thay thế phần giải thích đó.

## 4. Compiler phản ứng như thế nào?

### 4.1. Hai nhóm cảnh báo

`javac` phân biệt hai nhóm khi code **không deprecated** gọi/override API đã deprecated:

- **`[deprecation]`**: lời gọi tới API deprecated thông thường (`forRemoval=false`).
- **`[removal]`**: lời gọi tới API được đánh dấu `forRemoval=true`.

Ví dụ bật cả hai:

```bash
javac -encoding UTF-8 --release 17 \
  -Xlint:deprecation -Xlint:removal \
  -cp classes -d classes DeprecatedConsumer.java
```

`-Xlint:deprecation,removal` là cách viết tương đương gọn hơn. Trên các bản `javac` hiện hành, `removal` nằm trong nhóm lint mặc định bật, trong khi `deprecation` thường cần bật để xem cảnh báo từng lần dùng thay cho bản tóm tắt. Đừng dựa vào mặc định trong CI: cấu hình compiler/plugin rõ ràng.

Cảnh báo không tự làm code lỗi biên dịch. **`-Werror`** có thể khiến compilation thất bại khi có warning, nếu dự án chủ động bật chính sách đó.

### 4.2. `@SuppressWarnings` không phải giải pháp migration

Khi bắt buộc giữ tương thích ngắn hạn:

```java
@SuppressWarnings("deprecation")
static void temporaryOldCall() {
    ApiLifecycle.oldNormalize("abc");
}

@SuppressWarnings("removal")
static void temporaryRemovalCall() {
    ApiLifecycle.obsoleteNormalize("xyz");
}
```

Đây là **fragment minh họa** dùng cùng `ApiLifecycle` ở phần 5. `"deprecation"` và `"removal"` là **hai khóa khác nhau**: ẩn `[deprecation]` không đồng nghĩa ẩn `[removal]`. Chỉ suppress ở phạm vi nhỏ có lý do và kế hoạch bỏ, không tắt toàn bộ cảnh báo để làm build xanh. Suppression **không** giúp code liên kết thành công khi API bị xóa thật.

### 4.3. IDE và Javadoc

IDE thường đánh dấu phần tử deprecated, hiển thị Javadoc và gợi ý chuyển sang API mới. `javadoc` tạo nhãn **Deprecated** hoặc **Deprecated, for removal** và trang `deprecated-list.html` để liệt kê API đang deprecated. Tác giả thư viện cần bảo đảm phần văn bản `@deprecated` có hướng dẫn đủ rõ; metadata thuần túy không mô tả tác động kinh doanh/kỹ thuật của việc thay thế.

## 5. Bộ ví dụ Java 17+ hoàn chỉnh, đã chạy thực tế

Ví dụ này **không sử dụng API legacy của JDK**. Nó tự định nghĩa API cũ trong thư viện demo chỉ để minh họa cách đánh dấu và đọc metadata. Ba file cùng một thư mục, không cần dependency ngoài.

### 5.1. `ApiLifecycle.java`

```java
/** Demonstrates deprecation metadata. */
public final class ApiLifecycle {
    private ApiLifecycle() {}

    /**
     * Normalizes text.
     * @param value original text
     * @return trimmed text
     */
    public static String normalize(String value) {
        return value.trim();
    }

    /**
     * Old method.
     * @param value original text
     * @return trimmed text
     * @deprecated Since library version 2.1, use {@link #normalize(String)}.
     */
    @Deprecated(since = "2.1", forRemoval = false)
    public static String oldNormalize(String value) {
        return normalize(value);
    }

    /**
     * Variant planned for removal.
     * @param value original text
     * @return trimmed text
     * @deprecated Since library version 3.0, use {@link #normalize(String)}.
     */
    @Deprecated(since = "3.0", forRemoval = true)
    public static String obsoleteNormalize(String value) {
        return normalize(value);
    }

    /**
     * Old method without metadata.
     * @param value original text
     * @return trimmed text
     * @deprecated Use {@link #normalize(String)}.
     */
    @Deprecated
    public static String oldDefault(String value) {
        return normalize(value);
    }
}
```

- `normalize(String)` là phương thức **được khuyến nghị**.
- `oldNormalize` bị deprecated thông thường từ **version thư viện giả định 2.1**.
- `obsoleteNormalize` bị deprecated và dự định loại bỏ từ **version thư viện giả định 3.0**.
- `oldDefault` cố ý không ghi thuộc tính để quan sát giá trị mặc định.

### 5.2. `DeprecationDemo.java` — đọc metadata ở runtime

```java
import java.lang.reflect.Method;

/** Prints deprecation metadata without calling deprecated methods. */
public class DeprecationDemo {
    public static void main(String[] args) throws Exception {
        for (String name : new String[] {
                "oldNormalize", "obsoleteNormalize", "oldDefault"}) {
            Method method = ApiLifecycle.class.getMethod(name, String.class);
            Deprecated marker = method.getAnnotation(Deprecated.class);
            String since = marker.since().isEmpty()
                    ? "(empty)" : marker.since();
            System.out.printf("%s: since=%s, forRemoval=%s%n",
                    name, since, marker.forRemoval());
        }
        System.out.println("Replacement: " + ApiLifecycle.normalize("  HELLO  "));
    }
}
```

`@Deprecated` có `@Retention(RUNTIME)`, vì vậy reflection có thể đọc được trên method. Mã duyệt **theo thứ tự mảng tên** để stdout ổn định, không dựa vào thứ tự không được cam kết của `Class.getMethods()`. Vì ba method đều được annotate nên `marker` không null. Với chương trình tổng quát, luôn kiểm tra:

```java
Deprecated marker = method.getAnnotation(Deprecated.class);
if (marker != null) {
    System.out.println(marker.since());
    System.out.println(marker.forRemoval());
}
```

Đoạn bổ sung là **fragment trong nơi đã có biến `method` kiểu `java.lang.reflect.Method`**.

**Biên dịch và chạy** (JDK 17+):

```bash
mkdir -p classes
javac -encoding UTF-8 --release 17 -d classes ApiLifecycle.java DeprecationDemo.java
java -cp classes DeprecationDemo
```

Trên Windows PowerShell có thể dùng `mkdir classes` (nếu chưa tồn tại); lệnh `javac` trên một dòng như ví dụ là tương thích. **Stdout chính xác**, đã xác nhận với OpenJDK 24.0.2 và `--release 17`:

```text
oldNormalize: since=2.1, forRemoval=false
obsoleteNormalize: since=3.0, forRemoval=true
oldDefault: since=(empty), forRemoval=false
Replacement: HELLO
```

Bài học ở đây: `since`/`forRemoval` là dữ liệu sẵn trong annotation, runtime có thể đọc bằng reflection, nhưng việc gọi API cũ **không cần thiết** để đọc metadata.

### 5.3. `DeprecatedConsumer.java` — hai loại cảnh báo

```java
public class DeprecatedConsumer {
    public static void main(String[] args) {
        ApiLifecycle.oldNormalize("a");
        ApiLifecycle.obsoleteNormalize("b");
    }
}
```

Biên dịch file thứ ba để cố ý kích hoạt warning:

```bash
javac -encoding UTF-8 --release 17 \
  -Xlint:deprecation -Xlint:removal \
  -cp classes -d classes DeprecatedConsumer.java
```

Chú ý dấu `\` xuống dòng thuộc **Bash/Zsh**, không phải PowerShell; trên Windows có thể nhập tất cả trên một dòng.

**Các thông điệp cảnh báo cốt lõi đã quan sát khi kiểm thử:**

```text
warning: [deprecation] oldNormalize(String) in ApiLifecycle has been deprecated
warning: [removal] obsoleteNormalize(String) in ApiLifecycle has been deprecated and marked for removal
2 warnings
```

Đây là **bản trích phần cốt lõi, không phải stderr nguyên byte**: `javac` còn in vị trí file, số dòng và dấu `^`; các terminal/JDK có thể khác ở cách xuống dòng. Không chạy `DeprecatedConsumer` như cách sử dụng được khuyến nghị; mục đích duy nhất là quan sát compiler warning.

### 5.4. `javadoc` và `deprecated-list.html`

Chạy trong cùng thư mục:

```bash
javadoc -quiet -Xdoclint:all -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -d docs ApiLifecycle.java
```

Xem `docs/ApiLifecycle.html` và `docs/deprecated-list.html`. Trong thử nghiệm với OpenJDK 24.0.2, `javadoc` hoàn tất không lỗi, cả hai file HTML thực sự được sinh. Tài liệu của API cũ có phần hướng dẫn `@deprecated`, trong khi annotation quyết định metadata và cách Javadoc nhóm trạng thái.

## 6. Khi thay đổi `forRemoval` ở phiên bản thư viện mới

Giả sử API `legacyFormat` **lần đầu bị deprecated ở thư viện 2.1**:

```java
@Deprecated(since = "2.1", forRemoval = false)
public static String legacyFormat(String value) {
    return normalize(value);
}
```

Sau đó thư viện công bố **ý định xóa** ở phiên bản **3.0**. Khi cập nhật code:

```java
/**
 * Định dạng theo hợp đồng trước đây.
 *
 * @param value giá trị cần xử lý
 * @return chuỗi đã xử lý
 * @deprecated Kể từ 2.1, dùng {@link #normalize(String)}.
 *             Từ phiên bản 3.0, API này đã được lên kế hoạch loại bỏ.
 */
@Deprecated(since = "2.1", forRemoval = true)
public static String legacyFormat(String value) {
    return normalize(value);
}
```

Hai đoạn là **fragment trong một lớp có `normalize(String)`**. Quan trọng: vẫn **giữ `since="2.1"`** khi chuyển `forRemoval` từ false sang true. Lý do: metadata `since` lưu **mốc bắt đầu deprecated**, không phải mốc nâng cấp cảnh báo. Mốc quyết định loại bỏ ở 3.0 nên được ghi trong **Javadoc, release notes hoặc migration guide**, không ghi đè lịch sử.

Sơ đồ vòng đời một API minh họa:

```text
Thư viện 1.0          Thư viện 2.1                 Thư viện 3.0
API được giới thiệu → @Deprecated(since="2.1") → forRemoval=true
                               |                       |
                               |                       v
                               |             Công bố ý định xóa
                               v                       |
                    Đề xuất API thay thế              v
                                            Phiên bản tương lai do dự án
                                            quyết định: có thể xóa API
```

Đây **không** phải yêu cầu mọi thư viện phải trải qua đúng 3 giai đoạn hay có lịch xóa cố định. Tác giả có thể đặt `forRemoval=true` ngay từ lần đầu deprecated nếu chính sách đã rõ; việc xóa cần xem xét tương thích mã nguồn, binary và người dùng thực tế.

## 7. Cần hiểu gì về Java modules và phạm vi annotation?

`@Deprecated` là annotation chuẩn với `@Documented`, `@Retention(RUNTIME)`, và có `@Target` cho một số phần tử như **type, method, constructor, field, package, module, parameter và local variable**. Tuy nhiên, **không phải mọi vị trí đều gây compiler warning như method**:

- Đánh dấu `@Deprecated` lên **tham số, local variable hoặc package** không tự tạo cảnh báo deprecated tương ứng khi các phần tử đó được sử dụng.
- Nếu **module** được đánh dấu deprecated, sử dụng module trong chỉ thị `requires` có thể phát cảnh báo, nhưng việc dùng các type nằm bên trong module đó **không tự động** có nghĩa mọi type bị deprecated.
- Trên class/method/field được khai báo deprecated, compiler có thể cảnh báo khi phần tử được sử dụng hoặc override từ code không deprecated.

Không dùng `@Deprecated` làm công cụ validation của tham số hay runtime policy; nó là metadata tiến hóa API. Chỉ đặt khi muốn truyền đạt rõ trạng thái vòng đời.

## 8. Kiểm soát chất lượng khi phát hành thư viện

### Với tác giả API

1. Đưa ra **API thay thế** khả thi và tài liệu contract trước khi thông báo API cũ.
2. Ghi `@Deprecated(since = "x.y", forRemoval = false/true)` phản ánh đúng **phiên bản thư viện** và **ý định xóa**.
3. Ghi thẻ Javadoc `@deprecated`: lý do, link `{@link ...}` và các khác biệt quan trọng khi migration.
4. Thêm changelog/release notes và thông báo thời điểm nâng `forRemoval` nếu có.
5. Kiểm thử API thay thế; không để ví dụ tutorial mới gọi API đã bị deprecated.
6. Sinh Javadoc và kiểm tra `deprecated-list.html`; kiểm tra build với `-Xlint:dep-ann` để phát hiện Javadoc deprecated thiếu annotation.
7. Chỉ xóa API sau khi cân nhắc backward compatibility; xóa public API có thể gây lỗi biên dịch hoặc lỗi liên kết cho ứng dụng chưa nâng cấp.

### Với người dùng API

1. Bật các cảnh báo `-Xlint:deprecation,removal` ở trình biên dịch hoặc cấu hình tương đương trong Maven/Gradle.
2. Đọc **Javadoc đúng version** và release notes; metadata không mô tả đầy đủ semantics của replacement.
3. Ưu tiên xử lý lời gọi `[removal]`, đồng thời lập kế hoạch thay các lời gọi `[deprecation]`.
4. Viết test tích hợp để kiểm tra đầu ra/ngoại lệ sau khi chuyển API; tên thay thế nghe giống nhau không bảo đảm contract hoàn toàn tương đương.
5. Hạn chế `@SuppressWarnings` vào điểm chuyển tiếp có giải thích; suppression không ngăn JVM gặp lỗi nếu API bị xóa.

### Khi kiểm tra thư viện đã được biên dịch

`javac` phát hiện nhiều vấn đề khi **biên dịch source**. Khi xem JAR/class đã build từ trước, JDK hiện hành có công cụ **`jdeprscan`** để tìm các lời gọi tới **API Java SE đã deprecated**.

```bash
jdeprscan --for-removal classes
```

Trong câu lệnh trên, `classes` là thư mục class do ví dụ biên dịch. **Giới hạn quan trọng:** `jdeprscan` quét deprecated **Java SE APIs**, **không** báo mọi `@Deprecated` tự định nghĩa ở thư viện bên thứ ba hoặc lớp `ApiLifecycle` trong bài. Trong dự án thật, cần bổ sung cảnh báo compiler, phân tích dependency, tài liệu phát hành của thư viện bên ngoài; không xem kết quả trống từ `jdeprscan` là chứng nhận code không có deprecated API nào.

## 9. Lỗi thường gặp và cách tránh

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `@Deprecated(since="2.1")` báo lỗi khi build `--release 8` | Hai phần tử metadata được bổ sung từ Java 9. | Chọn API/cú pháp phù hợp target Java; nếu dự án còn hỗ trợ Java 8, cần tuân thủ khả năng của bản đó. |
| `since()` là chuỗi rỗng | Annotation không khai báo giá trị `since`. | Tác giả API nên điền mốc deprecated có ý nghĩa. |
| `forRemoval()` luôn false | Annotation không khai báo `forRemoval`; false là giá trị mặc định. | Chỉ đặt true khi chính sách có ý định xóa. |
| Trình biên dịch báo `[removal]` dù method còn tồn tại | `forRemoval=true` có nghĩa có ý định xóa, không phải API đã biến mất. | Chuyển sang replacement, xem tài liệu và version thực. |
| Build lỗi khi gặp warning | `-Werror` bật trong build. | Ưu tiên migration thay vì tắt toàn bộ warning. |
| `@SuppressWarnings("deprecation")` không che `[removal]` | Hai category khác nhau. | Chuyển API; nếu buộc phải tạm suppress, dùng đúng key và scope. |
| Javadoc không giải thích phương án thay thế | Thiếu thẻ `@deprecated` hoặc thiếu link. | Bổ sung hướng dẫn, ví dụ và liên kết `{@link}`. |
| `javac` báo `[dep-ann]` | Có tag Javadoc `@deprecated` nhưng không có annotation `@Deprecated`. | Thêm annotation cho phần tử phù hợp. |
| Đọc reflection ném `NullPointerException` | `getAnnotation(Deprecated.class)` trả null với phần tử chưa annotate. | Kiểm tra `marker != null` trước khi đọc. |
| `@since 1.0` khác `@Deprecated(since="2.1")` | Đó là hai sự kiện khác nhau. | Giữ đúng lịch sử xuất hiện và lịch sử deprecated. |
| `jdeprscan` không liệt kê deprecated của thư viện riêng | Công cụ tập trung vào Java SE. | Dùng compiler analysis, library docs và công cụ dependency phù hợp. |
| Đoán API xóa ở bản kế tiếp vì `forRemoval=true` | Metadata không có deadline. | Đọc lịch phát hành và migration guide chính thức. |

## 10. Tình huống kiểm thử tư duy

**Tình huống A:** một API được giới thiệu trong thư viện 1.4, lần đầu deprecated ở 2.0, và đến 3.0 mới thông báo có ý định xóa. Metadata ở 3.0 nên là:

```java
@Deprecated(since = "2.0", forRemoval = true)
```

Lý do: `since` lưu mốc **2.0**, mốc đầu tiên deprecated, không bị cập nhật theo version bắt đầu có `forRemoval=true`.

**Tình huống B:** một method chỉ khai báo `@Deprecated`. Reflection trả:

```text
since = ""
forRemoval = false
```

Không có thông tin version từ metadata, không tự suy đoán đó là 9.

**Tình huống C:** code dùng một phương thức có `forRemoval=true` mà thư viện vẫn cung cấp. Compiler phát warning, ứng dụng chưa chắc đã lỗi. Tuy nhiên việc thay thư viện trong một đợt nâng cấp sau này có thể làm **source không còn biên dịch** hoặc binary cũ gặp lỗi liên kết nếu method đã bị xóa.

**Tình huống D:** tác giả chỉ viết `@deprecated` trong Javadoc. Người đọc có thể thấy cảnh báo trong HTML nhưng bộ công cụ compiler có thể không nhận diện đúng annotation. Thực hành tốt là đặt **cả tag và annotation**.

## 11. Câu hỏi ôn tập

1. **`@Deprecated(since="4.0")` nghĩa API được giới thiệu ở 4.0?**  
   Không, nó bắt đầu **bị deprecated** ở 4.0.

2. **Giá trị mặc định của `since()` và `forRemoval()` là gì?**  
   `""` và `false`.

3. **`forRemoval=true` có bảo đảm bản phát hành kế tiếp sẽ xóa?**  
   Không, chỉ thông báo **ý định loại bỏ trong tương lai**.

4. **Vì sao cần cả `@Deprecated` và `@deprecated`?**  
   Annotation cung cấp metadata cho compiler/IDE/reflection; thẻ Javadoc giải thích lý do và API thay thế.

5. **`@since 1.0` và `@Deprecated(since="2.1")` có mâu thuẫn không?**  
   Không. API xuất hiện ở 1.0 và bị deprecated từ 2.1.

6. **Cảnh báo `[removal]` khác `[deprecation]`?**  
   `[removal]` liên quan đến `forRemoval=true`, thể hiện ý định xóa API trong tương lai.

7. **Làm sao đọc metadata ở runtime?**  
   Dùng reflection như `Method.getAnnotation(Deprecated.class)`, kiểm tra null, gọi `since()` và `forRemoval()`.

8. **Có nên suppress toàn bộ warning để vượt qua CI không?**  
   Không, ưu tiên di chuyển sang API hiện hành và dùng suppression phạm vi hẹp khi thật sự cần thiết.

## 12. Tài liệu chính thức còn hiệu lực

- [Java SE 26 — `java.lang.Deprecated`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Deprecated.html): ngữ nghĩa, hai element và mặc định, retention và khuyến nghị tài liệu.
- [Java Language Specification 26 — `@Deprecated`](https://docs.oracle.com/javase/specs/jls/se26/html/jls-9.html#jls-9.6.4.6): ordinary/terminally deprecated và quy tắc cảnh báo.
- [Java SE 26 — `javac`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `-Xlint:deprecation`, `-Xlint:removal`, `-Xlint:dep-ann` và `-Werror`.
- [Java SE 26 — `javadoc`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html): tạo documentation và kiểm tra HTML/Javadoc.
- [Java SE 26 — Deprecated API](https://docs.oracle.com/en/java/javase/26/docs/api/deprecated-list.html): danh mục API Java SE đang deprecated ở đúng phiên bản.
- [Java SE 26 — Removed APIs](https://docs.oracle.com/en/java/javase/26/migrate/removed-apis.html): hướng dẫn nâng cấp và `jdeprscan`.
- [OpenJDK JEP 277 — Enhanced Deprecation](https://openjdk.org/jeps/277): động cơ bổ sung `since`/`forRemoval` từ Java 9.
