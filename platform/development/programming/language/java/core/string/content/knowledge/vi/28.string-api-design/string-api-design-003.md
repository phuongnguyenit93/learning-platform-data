# Thiết kế API String: Quy định rõ cách xử lý null, rỗng và trắng

## 1. Vấn đề cốt lõi

Một API Java nhận `String` thường phải giải quyết ba trạng thái dễ bị đánh đồng:

1. **`null`**: không có đối tượng chuỗi. Tùy hợp đồng, có thể là “không truyền”, “không biết”, một giá trị được phép, hoặc dữ liệu không hợp lệ.
2. **Chuỗi rỗng `""` (empty)**: có đối tượng `String`, nhưng độ dài bằng 0. Có thể là giá trị người dùng đã nhập rồi xóa hết, hoặc nội dung hợp lệ như ghi chú trống.
3. **Chuỗi chỉ gồm ký tự trắng (blank)**: có ký tự nhưng toàn bộ được `String.isBlank()` coi là whitespace, ví dụ `"   "` hoặc `"\t\n"`. Chuỗi rỗng cũng được `isBlank()` trả `true`.

Ngoài ra, **chuỗi có nội dung** như `" A "` có thể chứa khoảng trắng đầu/cuối mà ứng dụng muốn giữ hoặc chuẩn hóa. Bài học này nằm trong chủ đề **thiết kế API**, nên trọng tâm là định nghĩa rõ ý nghĩa và hành vi tại ranh giới API, không chỉ gọi đúng phương thức thư viện.

Ví dụ API tạo tài khoản nhận tên hiển thị, mật khẩu và ghi chú:

- Tên hiển thị bắt buộc, `null`/rỗng/trắng đều không hợp lệ; có thể `strip()` rồi kiểm tra.
- Mật khẩu không cho phép `null` hoặc rỗng nhưng **không được tự động `trim()`/`strip()`**, vì dấu cách có thể là ký tự thật của mật khẩu theo chính sách hệ thống.
- Ghi chú có thể cho phép `null` (“chưa cung cấp”), `""` (“đã cung cấp nhưng trống”) và `"   "` (“nội dung gồm dấu cách”); nếu muốn gộp các trạng thái, phải ghi rõ.
- Với API cập nhật từng phần, trường *vắng mặt* và trường *có mặt với giá trị null* có thể có ý nghĩa khác nhau, ví dụ “không đổi” và “xóa giá trị”.

**Quy tắc nền tảng:** Không chuẩn hóa mọi chuỗi đầu vào bằng `null -> ""` hay `strip()` theo thói quen. Mỗi tham số phải có hợp đồng dữ liệu phù hợp.

## 2. Cách Java kiểm tra từng trạng thái

`String` trong Java 17 có các API sau:

| Biểu thức | Khi `s == null` | `s = ""` | `s = "   "` | `s = " hi "` |
| --- | --- | --- | --- | --- |
| `s == null` | `true` | `false` | `false` | `false` |
| `s.isEmpty()` | Ném `NullPointerException` | `true` | `false` | `false` |
| `s.isBlank()` | Ném `NullPointerException` | `true` | `true` | `false` |
| `s.length() == 0` | Ném `NullPointerException` | `true` | `false` | `false` |
| `s.strip().isEmpty()` | Ném `NullPointerException` | `true` | `true` với dấu cách thông thường | `false` |

Từ Java 11, `String.isBlank()` xác định liệu chuỗi trống hoặc chỉ chứa các code point mà `Character.isWhitespace(int)` nhận diện hay không. `isEmpty()` chỉ xét độ dài bằng 0 và **không cần duyệt từng ký tự**.

Khi `null` có thể xuất hiện, kiểm tra trước khi gọi phương thức:

```java
static boolean isNullOrBlank(String value) {
    return value == null || value.isBlank();
}
```

Phép `||` đánh giá ngắn mạch: nếu `value == null` là `true`, Java không gọi `isBlank()` nữa. Đây là **đoạn phương thức** đặt trong class Java, không phải chương trình độc lập.

Lưu ý: `isBlank()` trả `true` cho chuỗi rỗng, vì vậy không thể dùng riêng nó để phân biệt **empty** với **blank nhưng không empty**. Khi phân loại, nên kiểm tra theo thứ tự: `null` → `isEmpty()` → `isBlank()` → có nội dung.

## 3. Định nghĩa hợp đồng API trước khi lập trình

Một tài liệu API tốt cần trả lời rõ các câu hỏi: `null` có được phép không, `""` có nghĩa gì, khoảng trắng có được giữ không, có chuẩn hóa Unicode không, dữ liệu sai báo lỗi thế nào, và kết quả có bảo toàn đầu vào không.

Ví dụ bảng hợp đồng cho một hệ thống:

| Trường API | `null` | `""` | Chỉ có whitespace | Khoảng trắng đầu/cuối | Hành vi đề xuất |
| --- | --- | --- | --- | --- | --- |
| `displayName` | Không hợp lệ | Không hợp lệ | Không hợp lệ | `strip()` và lưu bản đã chuẩn hóa | Trả thông báo lỗi rõ ràng khi tên không hợp lệ |
| `password` | Không hợp lệ | Không hợp lệ | Có thể hợp lệ nếu chính sách cho phép | **Giữ nguyên** | Không sửa nội dung bí mật ngoài yêu cầu tường minh |
| `searchQuery` | Không lọc | Không lọc | Không lọc | `strip()` | Chuẩn hóa thành “không có bộ lọc” khi trống/trắng |
| `comment` | Chưa cung cấp | Đã cung cấp ghi chú rỗng | Giữ hoặc từ chối theo nghiệp vụ | Mặc định giữ nguyên | Không gộp ba trạng thái một cách ngầm định |
| `update.bio` | Có thể mang nghĩa xóa dữ liệu | Có thể mang nghĩa đặt bio rỗng | Có thể là dữ liệu hợp lệ | Theo chính sách | Phải tách khỏi trường vắng mặt trong yêu cầu cập nhật |

Bảng này là **ví dụ thiết kế**, không phải luật chung của Java. Hợp đồng cần được ghi trong Javadoc, OpenAPI/schema, validation, tài liệu client hoặc nơi thích hợp của dự án.

Một số điều kiện cần thống nhất ở cả **client, server, database**: một chuỗi rỗng có được lưu thành `""` hay thành `NULL`; có cắt khoảng trắng khi validate nhưng không cắt khi lưu; lỗi trả về loại gì; và cách biểu diễn một trường không hiện diện trong JSON.

## 4. Chiến lược xử lý: Reject, Normalize, Preserve

### 4.1. Reject — từ chối các trạng thái không hợp lệ

Dùng cho trường bắt buộc có dữ liệu có ý nghĩa, ví dụ tên hiển thị:

```java
import java.util.Objects;

static String requireNonBlankName(String raw) {
    Objects.requireNonNull(raw, "name must not be null");
    String normalized = raw.strip();

    if (normalized.isEmpty()) {
        throw new IllegalArgumentException("name must not be blank");
    }
    return normalized;
}
```

`Objects.requireNonNull` chủ động ném `NullPointerException` với thông điệp khi `raw` là null. `IllegalArgumentException` báo giá trị không phù hợp điều kiện nghiệp vụ. Đây là cách thiết kế cho một utility nội bộ; tại ranh giới HTTP, ứng dụng thường chuyển lỗi validation thành phản hồi 4xx có cấu trúc.

**Quan trọng:** Kiểm tra `raw.isBlank()` có thể từ chối blank trước khi chuẩn hóa, nhưng ví dụ trên kiểm tra chuỗi **sau khi strip** vì hợp đồng yêu cầu lưu chuỗi đã bỏ khoảng trắng đầu/cuối. Hai cách thống nhất với nhau khi dùng cùng quy tắc whitespace.

### 4.2. Normalize — chủ động gộp các trạng thái

Một ô tìm kiếm tùy chọn có thể định nghĩa “không có bộ lọc” khi query bằng `null`, rỗng hoặc toàn dấu cách:

```java
static String normalizeOptionalQuery(String raw) {
    if (raw == null) {
        return null;
    }
    String normalized = raw.strip();
    return normalized.isEmpty() ? null : normalized;
}
```

Bây giờ cả `null`, `""` và `" \t "` đều cho `null`, còn `"  java  "` cho `"java"`. Đây là **quyết định nghiệp vụ cố ý**, không phải chuẩn hóa bắt buộc cho mọi tham số String. Nếu cần lưu vết người dùng đã chủ động gửi chuỗi rỗng, không được dùng cách gộp này.

Nếu hợp đồng muốn **mọi trường đầu ra đều khác null**, có thể trả `""` để biểu diễn “không có nội dung”, nhưng phải ghi rõ điều đó và hiểu rằng đã mất phân biệt giữa absent và empty.

### 4.3. Preserve — giữ nguyên, chỉ kiểm tra điều kiện cần

Với mật khẩu (trong một chính sách cho phép dấu cách), không tự động strip:

```java
static String requireNonEmptyPassword(String raw) {
    Objects.requireNonNull(raw, "password must not be null");
    if (raw.isEmpty()) {
        throw new IllegalArgumentException("password must not be empty");
    }
    return raw; // Giữ nguyên cả khoảng trắng và các ký tự Unicode.
}
```

Trong hệ thống thực, có thể yêu cầu độ dài, độ phức tạp, danh sách ký tự hợp lệ và giới hạn kích thước theo chính sách xác thực. Ví dụ này chỉ minh họa **hợp đồng chuỗi**, không khuyến nghị mật khẩu chỉ có khoảng trắng.

Tương tự, mã định danh, token, chữ ký, nội dung được hash, văn bản giàu định dạng hoặc khoảng trắng có ý nghĩa **không nên** được tự ý `strip()`, `toLowerCase()` hay chuẩn hóa Unicode.

## 5. Ví dụ Java 17+ hoàn chỉnh

Tạo file **`StringInputPolicyDemo.java`**:

```java
import java.util.Objects;

public class StringInputPolicyDemo {
    enum Kind { NULL, EMPTY, BLANK, TEXT }

    static Kind kind(String value) {
        if (value == null) {
            return Kind.NULL;
        }
        if (value.isEmpty()) {
            return Kind.EMPTY;
        }
        return value.isBlank() ? Kind.BLANK : Kind.TEXT;
    }

    static String requireNonBlankName(String raw) {
        Objects.requireNonNull(raw, "name must not be null");
        String normalized = raw.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return normalized;
    }

    static String requireNonEmptyPassword(String raw) {
        Objects.requireNonNull(raw, "password must not be null");
        if (raw.isEmpty()) {
            throw new IllegalArgumentException("password must not be empty");
        }
        return raw;
    }

    static String normalizeOptionalQuery(String raw) {
        if (raw == null) {
            return null;
        }
        String normalized = raw.strip();
        return normalized.isEmpty() ? null : normalized;
    }

    public static void main(String[] args) {
        System.out.println("null=" + kind(null));
        System.out.println("empty=" + kind(""));
        System.out.println("blank=" + kind(" \t "));
        System.out.println("text=" + kind(" Java "));

        System.out.println("name=["
                + requireNonBlankName(" \t Lan \n") + "]");
        System.out.println("password-length="
                + requireNonEmptyPassword("   ").length());
        System.out.println("query-is-null="
                + (normalizeOptionalQuery(" \t ") == null));

        String unicodeSpace = "\u2003Java\u2003";
        System.out.println("strip-length=" + unicodeSpace.strip().length());
        System.out.println("trim-length=" + unicodeSpace.trim().length());
        System.out.println("nbsp-isBlank=" + "\u00A0".isBlank());

        try {
            requireNonBlankName(" \t ");
        } catch (IllegalArgumentException ex) {
            System.out.println("name-error=" + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 StringInputPolicyDemo.java
java StringInputPolicyDemo
```

Stdout:

```text
null=NULL
empty=EMPTY
blank=BLANK
text=TEXT
name=[Lan]
password-length=3
query-is-null=true
strip-length=4
trim-length=6
nbsp-isBlank=false
name-error=name must not be blank
```

Các kết quả đã được đối chiếu trên JDK với API có trong Java 17:

- `kind` kiểm tra `null` trước, rồi `isEmpty`, rồi `isBlank` nên không bị `NullPointerException` và giữ đủ bốn trạng thái.
- Tên được `strip` thành `Lan`; mật khẩu gồm ba dấu cách vẫn giữ độ dài 3, bởi hợp đồng hiện tại chỉ cấm rỗng.
- Query blank được hợp đồng gộp thành `null`.
- `\u2003` là EM SPACE được `strip()` nhận diện; `trim()` chỉ loại một số ký tự có mã nhỏ hơn hoặc bằng U+0020 nên không loại nó.
- `\u00A0` là NO-BREAK SPACE: trong Java, `Character.isWhitespace` không coi nó là whitespace, nên `isBlank()` trả `false`. Cần hiểu rõ định nghĩa “trắng” trong hợp đồng thay vì suy ra theo cảm nhận hiển thị.
- Một tên toàn whitespace thông thường bị từ chối và nhận lỗi có thông điệp.

## 6. Phân biệt trim(), strip() và isBlank() trong Unicode

### 6.1. trim() có tiêu chí lịch sử hẹp hơn

`String.trim()` loại ký tự ở hai đầu có mã `<= U+0020` theo đặc tả Java. `strip()` (Java 11+) dựa trên `Character.isWhitespace`; vì thế kết quả khác với một số dấu cách Unicode.

```java
String input = "\u2003Java\u2003";

System.out.println(input.trim().length());  // 6
System.out.println(input.strip().length()); // 4
```

Không phải tất cả ký tự thường gọi là “space” đều được `Character.isWhitespace` coi là whitespace: **NO-BREAK SPACE (U+00A0)** là ví dụ. Nếu hệ thống cần định nghĩa “trắng” theo quy tắc đặc thù (ví dụ coi U+00A0 là blank), hãy xây dựng validator chuẩn hóa theo một đặc tả được thống nhất và kiểm tra độc lập.

### 6.2. isBlank() không làm thay đổi chuỗi

`"  A  ".isBlank()` là `false`, vì có ký tự `A`. `isBlank()` không loại bỏ khoảng trắng ở hai đầu; `strip()` mới trả chuỗi mới sau chuẩn hóa. Đừng nhầm **kiểm tra** với **biến đổi**.

```java
String value = "  A  ";
System.out.println(value.isBlank());       // false
System.out.println("[" + value.strip() + "]"); // [A]
System.out.println("[" + value + "]");       // [  A  ]
```

`String` là immutable: `strip()` không thay đổi biến `value`. Muốn lưu bản chuẩn hóa, phải sử dụng giá trị trả về.

### 6.3. Không dùng isEmpty() để kiểm tra “người dùng chưa nhập”

Chuỗi `"    "` không rỗng, vì có ký tự. Nếu một form coi chuỗi toàn dấu cách là không hợp lệ, dùng `isBlank()` (sau kiểm tra null) hoặc `strip().isEmpty()`. Ngược lại, với dữ liệu nhạy với whitespace, chỉ dùng `isEmpty()` nếu hợp đồng yêu cầu.

## 7. Null trong tham số, giá trị trả về và trạng thái cập nhật

### 7.1. Tham số bắt buộc và tùy chọn

Với tham số bắt buộc, API nên nêu rõ “non-null” và điều kiện rỗng/trắng. Một hàm nhận tên hiển thị có thể dùng Javadoc:

```java
/**
 * Lưu tên hiển thị sau khi strip khoảng trắng hai đầu.
 *
 * @param name giá trị non-null, sau strip phải có ít nhất một ký tự
 *             không phải whitespace theo Character.isWhitespace
 * @return tên đã chuẩn hóa, khác null và không blank
 * @throws NullPointerException nếu name là null
 * @throws IllegalArgumentException nếu name blank
 */
static String validateDisplayName(String name) {
    Objects.requireNonNull(name, "name");
    String normalized = name.strip();
    if (normalized.isEmpty()) {
        throw new IllegalArgumentException("blank name");
    }
    return normalized;
}
```

Đây là đoạn phương thức độc lập về ý nghĩa nhưng cần đặt trong một class để biên dịch. Đối với API công khai, có thể chọn cùng một kiểu lỗi validation cho cả null và blank, miễn là **hợp đồng và test thể hiện nhất quán**; ví dụ trên cố ý phân biệt lỗi do null và do giá trị không hợp lệ.

Với giá trị **trả về**, nên thống nhất liệu `null` biểu thị “không tìm thấy” hay ngoại lệ, `""` có phải giá trị hợp lệ không. Có thể dùng `Optional<String>` cho kết quả có thể không hiện diện:

```java
static java.util.Optional<String> normalizedQuery(String raw) {
    if (raw == null || raw.isBlank()) {
        return java.util.Optional.empty();
    }
    return java.util.Optional.of(raw.strip());
}
```

`Optional.empty()` cho phép thể hiện “không có kết quả” rõ ràng; nhưng nó cũng **gộp** null và blank theo chính sách. `Optional` không tự thay thế việc quyết định rỗng/trắng, và không cần dùng ở mọi field hoặc tham số chỉ để né thiết kế hợp đồng.

### 7.2. API cập nhật từng phần cần phân biệt vắng mặt với null

Giả sử một request cập nhật hồ sơ có trường `bio`. Ba trạng thái đầu vào có thể mang nghĩa:

| Trạng thái request | Ý nghĩa ví dụ |
| --- | --- |
| Không có thuộc tính `bio` | Giữ nguyên bio hiện tại |
| Có `bio: null` | Xóa/clear bio (nếu API cho phép) |
| Có `bio: ""` | Đặt bio thành chuỗi rỗng |
| Có `bio: "   "` | Đặt thành ba dấu cách hoặc từ chối theo quy định |

Một đối tượng chỉ có field `String bio` đôi khi không thể phân biệt **vắng mặt** với **có mặt nhưng null** sau khi deserialization. Nếu hợp đồng cần phân biệt, request model phải mang cả trạng thái **field present** và giá trị của nó, hoặc dùng một cơ chế cập nhật có ngữ nghĩa định nghĩa rõ như JSON Merge Patch. Không tự coi `null` là “không cập nhật” nếu protocol quy định `null` là “xóa”.

### 7.3. Đừng biến null thành empty ở quá nhiều tầng

Nếu HTTP binder, service và repository mỗi nơi tự dùng một quy tắc khác nhau, dữ liệu có thể thay đổi ý nghĩa giữa các tầng. Nên chuẩn hóa ở một **ranh giới có hợp đồng rõ**, rồi truyền giá trị đã được validate vào lớp sau dưới invariant được mô tả. Ví dụ service nhận `displayName` đã non-null và non-blank; repository không tự gọi `strip()` một lần nữa theo một tiêu chí khác.

## 8. Lỗi và cách thông báo cho caller

Một API tốt nêu rõ phản ứng khi dữ liệu không hợp lệ:

- **Java method nội bộ:** `Objects.requireNonNull` hoặc kiểm tra thủ công; `IllegalArgumentException` cho vi phạm giá trị; thông điệp xác định tên trường và yêu cầu. Thống nhất loại lỗi trong cùng nhóm API.
- **REST/HTTP:** một lỗi xác thực input thường được map sang mã lỗi phía client (thường là HTTP 400 hoặc mã phù hợp quy ước API) kèm field, reason/code và thông điệp rõ ràng. Không phơi bày dữ liệu bí mật trong lỗi hoặc log.
- **Validation ở DTO/schema:** khai báo điều kiện phù hợp (`non-null`, `non-empty`, `non-blank`) rồi đảm bảo cấu hình binder và validation thực sự chạy. Trong Jakarta Bean Validation, các annotation thường dùng là `@NotNull`, `@NotEmpty` và `@NotBlank`; đây là **thư viện phụ thuộc**, không phải annotation Java SE 17 có sẵn.
- **Database:** kiểm tra khả năng lưu `NULL`/`""`, ràng buộc cột và quy tắc so sánh. Một số hệ quản trị có cách xử lý chuỗi rỗng khác nhau; đừng dựa vào giả định giữa các database.

Không trả “invalid” chung chung nếu client cần biết trường nào sai. Nhưng khi field chứa password, token hoặc dữ liệu nhạy cảm, thông điệp và log không nên chép toàn bộ input.

## 9. Thiết kế test theo bảng trạng thái

Đối với một tham số, các trường hợp test nên bao phủ cả **trạng thái** và **biến thể ký tự trắng**. Ví dụ hợp đồng `requireNonBlankName`:

| Đầu vào | Kết quả mong đợi |
| --- | --- |
| `null` | `NullPointerException` theo hợp đồng ví dụ |
| `""` | `IllegalArgumentException` |
| `"   "` | `IllegalArgumentException` |
| `"\t\n"` | `IllegalArgumentException` |
| `" A "` | Trả `"A"` |
| `"A B"` | Giữ khoảng trắng nội bộ, trả `"A B"` |
| `"\u2003A\u2003"` | Trả `"A"` |
| `"\u00A0"` | Không được coi là blank bằng `isBlank()` mặc định; cần quyết định nghiệp vụ |
| Chuỗi quá dài | Có thể bị từ chối nếu hợp đồng đặt giới hạn độ dài |

Nếu có giới hạn độ dài, nêu rõ **đơn vị đo**: `String.length()` đếm **UTF-16 code unit**, không nhất thiết bằng số Unicode code point hoặc số ký tự người dùng nhìn thấy. Ví dụ một emoji ngoài BMP thường có `length() == 2` và `codePointCount(...) == 1`. Không dùng một tiêu chí độ dài để diễn giải thành tiêu chí khác.

Tránh viết test chỉ chứng minh `String.isBlank()` hoạt động theo JDK; test có giá trị là xác nhận **hợp đồng nghiệp vụ của API**, gồm cả lỗi, chuẩn hóa và hành vi bảo toàn whitespace.

## 10. Những sai lầm phổ biến

1. **Gọi `s.isBlank()` khi `s` có thể là null.** Kết quả là `NullPointerException` ngoài ý muốn. Kiểm tra null trước hoặc đặt invariant non-null ngay đầu method.
2. **Coi `isEmpty()` và `isBlank()` như nhau.** `"  "` không empty nhưng blank.
3. **Coi null và chuỗi rỗng là một.** Có thể làm mất ý nghĩa “chưa cung cấp” so với “cung cấp rỗng”, nhất là trong cập nhật.
4. **Luôn strip mọi input.** Có thể thay đổi mật khẩu, token, định danh, chữ ký hoặc nội dung được yêu cầu giữ nguyên.
5. **Chỉ kiểm tra blank rồi không dùng bản chuẩn hóa.** Nếu yêu cầu đầu ra phải bỏ khoảng trắng hai đầu, phải trả/lưu giá trị của `strip()`.
6. **Nhầm `trim()` và `strip()`.** Hai phương thức khác nhau ở một số Unicode whitespace; không phải tất cả ký tự trông như khoảng trắng đều bị loại bởi `strip()`.
7. **Tự động biến mọi blank thành null mà không có thỏa thuận.** Có thể làm mất dữ liệu người dùng đã chủ động gửi.
8. **Định nghĩa null khác nhau giữa Java service và HTTP/JSON.** Tham số String không đủ thể hiện mọi trạng thái field-present; phải giữ trạng thái hiện diện nếu cần.
9. **Giả định annotation validation tự hoạt động.** `@NotBlank` yêu cầu framework/provider được cấu hình và thực thi; Java SE không tự áp dụng ràng buộc đó.
10. **Trả lỗi không nhất quán.** Một API từ chối null bằng NPE, API khác âm thầm đổi thành rỗng; người dùng và hệ thống tích hợp khó dự đoán.
11. **Bỏ qua chuỗi Unicode đặc biệt.** U+00A0, U+2003, zero-width characters và normalization có thể dẫn đến kết quả khác với kỳ vọng. Hãy định nghĩa nhóm ký tự được chấp nhận nếu có yêu cầu bảo mật hoặc nghiệp vụ.
12. **Hiểu sai kích thước String.** `length()` đo đơn vị UTF-16; API có quy định số ký tự hiển thị nên chọn tiêu chí và test thích hợp.

## 11. Bài tập tự kiểm tra

### Bài 1 — Phân loại chính xác bốn trường hợp

Viết `kind(String)` để phân loại `null` → `NULL`, `""` → `EMPTY`, `" \t"` → `BLANK`, `"x"` → `TEXT`. Giải pháp có trong chương trình `StringInputPolicyDemo`: kiểm tra null trước, tiếp đến empty, rồi blank. Nếu kiểm tra `isBlank` trước `isEmpty` thì chuỗi rỗng sẽ bị xếp chung vào BLANK và làm mất một trạng thái cần phân biệt.

### Bài 2 — Thiết kế chính sách nhập tag

Đề bài: tag phải có nội dung sau khi loại khoảng trắng đầu/cuối, được viết thường (cho tag ASCII), null không hợp lệ.

```java
static String normalizeAsciiTag(String raw) {
    java.util.Objects.requireNonNull(raw, "tag must not be null");
    String tag = raw.strip();
    if (tag.isEmpty()) {
        throw new IllegalArgumentException("tag must not be blank");
    }
    return tag.toLowerCase(java.util.Locale.ROOT);
}
```

Đây là đoạn phương thức. `Locale.ROOT` giúp phép biến đổi chữ hoa/thường độc lập locale mặc định, nhưng không tự bảo đảm đúng mọi quy tắc định danh Unicode phức tạp. Chỉ dùng chuẩn hóa chữ thường khi hợp đồng tag thật sự không phân biệt chữ hoa.

### Bài 3 — Dữ liệu trống trong PATCH

Một request không có `nickname`, một request có `nickname: null`, một request có `nickname: ""`. Hãy thiết kế ý nghĩa cho từng trường hợp trước khi viết DTO. Gợi ý: “giữ nguyên”, “xóa”, “đặt rỗng” là một cách phân biệt; nếu cả null và rỗng đều có nghĩa là xóa, đó phải là quy tắc được ghi trong hợp đồng.

### Bài 4 — Password có dấu cách

Với `password = "  secret  "`, tại sao gọi `strip()` trước khi đối chiếu hash có thể sai? Vì đã thay đổi dữ liệu mà người dùng nhập. Hệ thống xác thực phải dùng quy tắc chuẩn hóa được công bố và nhất quán từ lúc thiết lập đến lúc kiểm tra, chứ không tự bỏ ký tự.

### Bài 5 — Trường hiển thị toàn whitespace Unicode

Một form nhận `"\u2003"` (EM SPACE) và `"\u00A0"` (NO-BREAK SPACE). `String.isBlank()` coi trường hợp đầu là blank nhưng không coi trường hợp thứ hai là blank. Hãy quyết định rõ trường hợp thứ hai được phép hay cần validator tùy biến; kết quả không thể suy ra chỉ từ “trông như khoảng trắng”.

## 12. Checklist khi công bố API

Trước khi triển khai một tham số hoặc field kiểu `String`, hãy kiểm tra:

- Có cho phép **null**, **empty** và **blank** một cách độc lập không?
- Có phân biệt **field absent** với **field present = null** trong thao tác cập nhật không?
- Có giữ hay loại whitespace ở đầu/cuối, khoảng trắng bên trong và ký tự Unicode đặc biệt không?
- Chuẩn hóa được thực hiện ở đâu, trước hay sau validation, và giá trị nào được truyền sang tầng tiếp theo?
- Giá trị không hợp lệ tạo lỗi gì, có thể dự đoán được không, có rò dữ liệu nhạy cảm không?
- Kết quả có bất biến/invariant nào, ví dụ “tên đã normalize, non-null, non-blank”?
- Độ dài tối đa được đo bằng UTF-16 code unit, Unicode code point hay quy tắc khác?
- Các ví dụ, schema, test và tài liệu client có dùng cùng chính sách không?

**Kết luận:** `null`, `""` và chuỗi chỉ chứa whitespace có ý nghĩa khác nhau. Java cung cấp `isEmpty()`, `isBlank()`, `trim()`, `strip()` và `Objects.requireNonNull()`, nhưng **chính API phải quyết định lúc nào từ chối, chuẩn hóa hay giữ nguyên**. Viết hợp đồng rõ ràng giúp caller dự đoán chính xác dữ liệu được chấp nhận, lưu giữ và trả về, đặc biệt khi có Unicode, cập nhật từng phần và nhiều tầng hệ thống.

**Tài liệu tham khảo:** [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Java SE 17 — Character.isWhitespace](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#isWhitespace(int)), [Java SE 17 — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)), [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).