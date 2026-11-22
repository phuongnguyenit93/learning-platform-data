# Dùng `@Deprecated`, `since` và `forRemoval` để truyền đạt lộ trình

Trong quá trình tiến hóa API Java, không phải phương thức hoặc lớp nào cũng có thể bị xóa ngay khi xuất hiện một thiết kế tốt hơn. Ứng dụng khác có thể đang gọi API đó, thư viện có thể được phát hành độc lập, và một số khách hàng cần thời gian để nâng JDK hoặc dependency. **Deprecation** là cơ chế thông báo rằng một API không còn được khuyến nghị sử dụng, đồng thời tạo khoảng chuyển tiếp để người dùng di chuyển sang giải pháp thay thế.

Từ Java 9, annotation `@Deprecated` có hai thuộc tính quan trọng là `since` và `forRemoval`. Kết hợp chúng với Javadoc, release notes và chính sách hỗ trợ phiên bản sẽ giúp tác giả API truyền đạt rõ ba thông tin: **API bắt đầu bị phản đối từ phiên bản nào, có dự định loại bỏ hay không, và người dùng nên chuyển sang đâu**.

Bài học thuộc nhóm **Tiến hóa API** của module **Java Advance Compatibility Migration**. Nội dung áp dụng cho người duy trì thư viện, framework, SDK hoặc API dùng chung trong một hệ thống nhiều module, đặc biệt khi cần giữ tương thích trong quá trình nâng JDK và phiên bản dependency.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Hiểu `@Deprecated` tác động thế nào đến compiler, tài liệu và người sử dụng API.
- Dùng đúng `since` và `forRemoval` để mô tả trạng thái và định hướng vòng đời API.
- Phân biệt thuộc tính `since` của annotation với thẻ `@since` và `@deprecated` trong Javadoc.
- Thiết kế đường chuyển đổi từ API cũ sang API mới mà vẫn có thời gian tương thích.
- Nhận diện cảnh báo của `javac`, dùng công cụ rà soát API deprecated và lập kế hoạch nâng cấp.
- Viết release notes, hướng dẫn migration và tiêu chí loại bỏ API có thể kiểm tra được.

## 2. `@Deprecated` thực sự có ý nghĩa gì?

`java.lang.Deprecated` là một annotation chuẩn. Khi gắn lên một API, tác giả thông báo rằng API đó không còn được khuyến nghị cho mã mới. Lý do có thể là thiết kế không còn phù hợp, đã có giải pháp thay thế, hành vi gây hiểu lầm, giới hạn bảo mật, hoặc kế hoạch loại bỏ tính năng.

Ví dụ đơn giản:

```java
public final class UserApi {
    private UserApi() {}

    @Deprecated
    public static String lookup(String userId) {
        return findNameById(userId);
    }

    public static String findNameById(String userId) {
        return "user-" + userId;
    }
}
```

Client mới nên gọi `findNameById`, nhưng `lookup` vẫn tồn tại và có thể được gọi. `@Deprecated` **không** tự động xóa method, ngăn thực thi, đổi kết quả trả về hay lên lịch loại bỏ. Nó truyền tín hiệu đến compiler, IDE, công cụ phân tích và người dùng API.

Các hệ quả thường gặp:

- Khi source khác sử dụng API deprecated, `javac` có thể phát cảnh báo; IDE thường đánh dấu lời gọi và gợi ý xem tài liệu thay thế.
- Javadoc có thể hiển thị API trong danh mục deprecated và giải thích lộ trình nếu được viết đầy đủ.
- Công cụ phân tích tương thích có thể thống kê các điểm sử dụng API cũ để phục vụ migration.
- API vẫn là một phần của binary public cho đến khi nhà phát triển thật sự thay đổi hoặc xóa nó.

Không nên dùng `@Deprecated` như một nhãn chung cho mọi đoạn mã ít được sử dụng. Cần xác định lý do và phương án thay thế; nếu không có đường chuyển đổi, cảnh báo sẽ khó mang lại hành động cụ thể.

## 3. `since` và `forRemoval` trong Java 9 trở lên

Từ Java 9, `@Deprecated` cho phép khai báo thêm hai phần tử:

```java
@Deprecated(since = "2.4", forRemoval = false)
public static String lookup(String userId) {
    return findNameById(userId);
}
```

### 3.1. `since`: API bị deprecated từ phiên bản nào?

`since` là một chuỗi (`String`) mô tả **phiên bản bắt đầu đánh dấu deprecated**. Với API của JDK, giá trị có thể là phiên bản Java; với API thuộc thư viện riêng, giá trị thường là phiên bản phát hành của chính thư viện đó.

Ví dụ:

```java
@Deprecated(since = "2.4")
public void connectLegacy() { /* ... */ }
```

Ở đây, `2.4` chỉ có ý nghĩa khi gắn với quy ước version của thư viện. Nó không tự động có nghĩa là Java 2.4, JDK 24 hoặc một mốc lịch cụ thể.

Những điểm cần nhớ:

- `since` trả lời câu hỏi **“Bị deprecated từ release nào?”**, không phải “API lần đầu xuất hiện ở release nào?”.
- Giá trị này là metadata để đọc hiểu; compiler không tự đối chiếu nó với lịch phát hành và không yêu cầu một định dạng version cố định.
- Nếu chưa khai báo, giá trị mặc định của `since` là chuỗi rỗng, tức chưa có thông tin phiên bản trong annotation.
- Khi về sau thay `forRemoval` từ `false` sang `true`, thông thường vẫn giữ nguyên `since` để bảo toàn lịch sử bắt đầu deprecated; mốc chuyển sang trạng thái dự kiến loại bỏ có thể ghi trong release notes.

### 3.2. `forRemoval`: API có được dự định loại bỏ không?

`forRemoval` là giá trị boolean:

```java
@Deprecated(since = "2.4", forRemoval = false)
public void oldOperation() { /* ... */ }
```

`false` cho biết API bị phản đối sử dụng nhưng **chưa được đánh dấu là dự kiến loại bỏ**. Đây cũng là giá trị mặc định, nên `@Deprecated(since = "2.4")` tương đương với việc khai báo `forRemoval = false`.

Khi API bước vào giai đoạn dự kiến xóa:

```java
@Deprecated(since = "2.4", forRemoval = true)
public void oldOperation() { /* ... */ }
```

`true` là tín hiệu mạnh hơn: tác giả có **ý định loại bỏ API trong một phiên bản tương lai**. Tuy nhiên, annotation này không có trường `removeIn` và không bảo đảm API sẽ bị xóa vào một ngày cụ thể. Mốc dự kiến, điều kiện và ngoại lệ phải được ghi trong chính sách hỗ trợ hoặc release notes.

### 3.3. Cách hiểu nhanh ba dạng khai báo

| Khai báo | Ý nghĩa | Thông tin còn thiếu |
| --- | --- | --- |
| `@Deprecated` | API không còn được khuyến nghị. | Chưa ghi release bắt đầu deprecate; chưa đánh dấu dự kiến loại bỏ. |
| `@Deprecated(since = "2.4")` | API bị deprecated từ release 2.4. | Không có ý định loại bỏ được khai báo; chưa chỉ ra API thay thế. |
| `@Deprecated(since = "2.4", forRemoval = true)` | API bị deprecated từ 2.4 và hiện được dự kiến loại bỏ. | Chưa cho biết khi nào xóa và cách migration. |

Khi thông báo cho người dùng, nên đi kèm cả lý do và đường chuyển đổi. `since` và `forRemoval` một mình không thay thế được tài liệu.

### 3.4. Chú ý khi vẫn phải biên dịch bằng Java 8

Java 8 đã hỗ trợ `@Deprecated` nhưng chưa có hai phần tử annotation `since` và `forRemoval`. Vì vậy, source cần compile bằng API Java 8 nên dùng:

```java
/**
 * @deprecated Kể từ phiên bản 2.4 của thư viện, dùng {@link #findById(String)}.
 */
@Deprecated
public String findLegacy(String id) {
    return findById(id);
}
```

Nếu thư viện vẫn cam kết hỗ trợ Java 8, không tự thêm `@Deprecated(since = ..., forRemoval = ...)` vào source được biên dịch với `--release 8`. Compiler sẽ kiểm tra API annotation theo Java 8, nơi chưa có các phần tử đó. Có thể giữ metadata về thời điểm deprecation trong Javadoc và release notes; chỉ dùng các phần tử mới khi minimum source/API release cho phép.

## 4. Phân biệt annotation và các thẻ Javadoc

Có ba thành phần dễ nhầm lẫn vì tên gần giống nhau:

| Cú pháp | Nằm ở đâu? | Trả lời câu hỏi |
| --- | --- | --- |
| `@Deprecated(since = "2.4")` | Annotation trong source Java | API bị đánh dấu deprecated từ release nào? |
| `@since 1.0` | Thẻ trong Javadoc | API được giới thiệu lần đầu từ release nào? |
| `@deprecated ...` | Thẻ trong Javadoc | Vì sao API không nên dùng và thay bằng gì? |

`@since` trong Javadoc mô tả **phiên bản API xuất hiện**, không phải phiên bản nó bị deprecated. Trong khi đó, `@deprecated` viết bằng chữ thường trong Javadoc là nơi giải thích nguyên nhân, cách chuyển đổi và liên kết đến API thay thế. Cả hai là thẻ tài liệu, không phải thuộc tính Java annotation.

Ví dụ đầy đủ:

```java
package com.example.accounts;

public final class AccountApi {
    private AccountApi() {}

    /**
     * Trả về tên tài khoản theo mã định danh.
     *
     * @param id mã tài khoản
     * @return tên tài khoản
     * @since 1.0
     * @deprecated Kể từ 2.4, hãy dùng
     *             {@link #findNameById(String)}. Phương thức cũ
     *             được giữ để các client có thời gian nâng cấp.
     */
    @Deprecated(since = "2.4", forRemoval = false)
    public static String getName(String id) {
        return findNameById(id);
    }

    /**
     * Tra cứu tên tài khoản theo mã định danh.
     *
     * @param id mã tài khoản
     * @return tên tài khoản
     * @since 2.4
     */
    public static String findNameById(String id) {
        return "account-" + id;
    }
}
```

Trong ví dụ:

- `getName` được giới thiệu từ 1.0 nhưng chỉ bị deprecated từ 2.4.
- `findNameById` là API mới xuất hiện trong 2.4.
- Annotation mô tả trạng thái máy có thể đọc; Javadoc giải thích cách người dùng phải hành động.
- Việc giữ `getName` gọi tiếp đến `findNameById` là một cách duy trì hành vi cũ trong giai đoạn chuyển tiếp, miễn là hai method thực sự có contract tương đương.

Khi viết Javadoc, ưu tiên `{@link ...}` đến đúng method hoặc class thay thế, mô tả khác biệt về giá trị trả về, exception, nullability và hành vi nếu có. Một câu “API này đã cũ” không đủ giúp người dùng sửa mã.

## 5. Thiết kế lộ trình tiến hóa API có các giai đoạn rõ ràng

Deprecation hữu ích nhất khi nằm trong một kế hoạch phát hành mà người sử dụng có thể theo dõi.

### 5.1. Ví dụ một lộ trình nhiều phiên bản

Giả sử thư viện `account-client` có API `getName()` từ phiên bản 1.0. Nhóm phát triển muốn chuyển sang `findNameById()` và dự định loại bỏ API cũ trong một major release. Một lộ trình minh họa:

| Phiên bản thư viện | Trạng thái API cũ | Công việc của nhà phát triển |
| --- | --- | --- |
| 1.0 | API đang hỗ trợ | Công bố contract sử dụng và kiểm thử bình thường. |
| 2.4 | Deprecated, `forRemoval = false` | Thêm API thay thế, Javadoc, ví dụ chuyển đổi và thông báo trong release notes. |
| 3.0 | Deprecated, `forRemoval = true` | Giữ API tương thích trong giai đoạn cuối, cảnh báo mạnh hơn và công bố mục tiêu loại bỏ. |
| 4.0 | Loại bỏ theo kế hoạch | Xóa API cũ khi đủ điều kiện, cập nhật API diff, migration guide và release notes. |

Đây chỉ là mô hình minh họa; dự án phải tuân theo chính sách versioning và thời gian hỗ trợ thực tế. Một API có thể cần nhiều release để chuyển đổi, hoặc phải xử lý nhanh hơn nếu có rủi ro nghiêm trọng.

Khi chuyển sang giai đoạn 3.0, giữ metadata phiên bản deprecated ban đầu:

```java
/**
 * @since 1.0
 * @deprecated Kể từ 2.4, dùng {@link #findNameById(String)}.
 *             Dự kiến loại bỏ theo lộ trình công bố cho 4.0.
 */
@Deprecated(since = "2.4", forRemoval = true)
public static String getName(String id) {
    return findNameById(id);
}
```

Trong release notes 3.0, cần ghi rõ rằng `forRemoval` vừa chuyển sang `true`. Không đổi `since` thành `3.0` vì như vậy sẽ mất dấu thời điểm API bắt đầu deprecated.

### 5.2. Điều kiện để chuyển sang `forRemoval = true`

Trước khi đánh dấu dự kiến loại bỏ, nhóm duy trì API nên biết:

- API thay thế đã sẵn sàng và có tài liệu đủ dùng chưa?
- API thay thế có được hỗ trợ trên các JDK và môi trường mà khách hàng đang sử dụng không?
- Người dùng đã có thời gian và công cụ cần thiết để migration chưa?
- Có những client, plugin, SDK hoặc dịch vụ độc lập nào vẫn phụ thuộc vào API cũ?
- Việc loại bỏ thuộc một major release hay có ngoại lệ theo chính sách phiên bản?
- Có cơ chế hỗ trợ khách hàng và phương án trì hoãn nếu mức độ ảnh hưởng cao không?

`forRemoval = true` nên là một quyết định có trách nhiệm về compatibility, không chỉ là cách làm cảnh báo nổi bật hơn.

### 5.3. Khi nào nên giữ deprecated API lâu dài?

Có trường hợp API cũ vẫn cần tồn tại vì hợp đồng hỗ trợ dài hạn, hệ thống legacy khó nâng cấp hoặc chi phí thay đổi quá cao. Khi chưa có quyết định loại bỏ, `forRemoval = false` là tín hiệu phù hợp hơn.

Tuy vậy, việc giữ API không có nghĩa phải khuyến khích dùng API đó cho mã mới. Nhà phát triển vẫn có thể hướng mọi sử dụng mới sang API được thiết kế lại, đồng thời duy trì behavior cũ với test và tài liệu rõ ràng.

## 6. Thay thế API mà không làm hỏng client quá sớm

### 6.1. Giữ entry point cũ trong giai đoạn chuyển tiếp

Nếu API mới tương đương với API cũ, cách đơn giản là để method cũ chuyển tiếp sang method mới:

```java
public class Formatter {
    public String formatText(String input) {
        return input == null ? "" : input.trim();
    }

    /**
     * @deprecated Kể từ 2.1, dùng {@link #formatText(String)}.
     */
    @Deprecated(since = "2.1", forRemoval = false)
    public String normalize(String input) {
        return formatText(input);
    }
}
```

Giữ tên, descriptor và mức truy cập của `normalize` giúp các lời gọi cũ tiếp tục liên kết trong những tình huống bình thường. Tuy nhiên, vẫn cần kiểm tra behavior: nếu `formatText` mới thay đổi xử lý `null`, locale, exception hoặc chuẩn hóa dữ liệu, không thể mặc định hai API tương đương.

### 6.2. Nếu contract mới khác contract cũ

Khi API mới thay đổi kiểu trả về, kiểu tham số hoặc xử lý lỗi, việc chuyển tiếp một dòng có thể không an toàn. Nên đặt một adapter xử lý khác biệt:

```java
public enum Mode { FAST, SAFE }

public final class Decoder {
    public byte[] decode(String text, Mode mode) {
        // Chi tiết giải mã thuộc implementation của thư viện.
        return text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
    }

    /**
     * @deprecated Kể từ 2.0, gọi {@link #decode(String, Mode)}
     *             và chỉ định chế độ mong muốn.
     */
    @Deprecated(since = "2.0", forRemoval = false)
    public byte[] decode(String text) {
        return decode(text, Mode.SAFE);
    }
}
```

Ví dụ minh họa việc cố định hành vi mặc định cũ thông qua một tham số mới. Trong dự án thực tế, implementation và adapter phải giữ các quy tắc đã công bố của API cũ; không nên thay đổi ngầm kết quả chỉ vì đã deprecated.

### 6.3. Không xóa API chỉ vì vừa gắn `@Deprecated`

Với thư viện phát hành độc lập, client có thể tồn tại dưới dạng binary đã biên dịch. Nếu xóa hoặc đổi descriptor của method mà client còn gọi, runtime có thể gặp lỗi như `NoSuchMethodError`. Với class bị xóa, có thể xuất hiện `NoClassDefFoundError` hoặc `ClassNotFoundException` tùy cách nạp.

Vì vậy, deprecation nên đi trước removal trong một lộ trình có thông báo, trừ trường hợp đặc biệt mà tổ chức chấp nhận thay đổi phá tương thích. Khi quyết định xóa, kiểm tra cả source clients và binary clients, không chỉ build của chính thư viện.

## 7. Tác động tới compiler và công cụ phân tích

### 7.1. Phát hiện lời gọi deprecated bằng `javac`

Với source client:

```java
public final class Client {
    public static void main(String[] args) {
        System.out.println(AccountApi.getName("a123"));
    }
}
```

Có thể biên dịch với các tùy chọn diagnostic:

```bash
javac -Xlint:deprecation -Xlint:removal \
  -cp path/to/account-client.jar \
  Client.java
```

Ví dụ dùng dấu `\` để nối dòng trong shell kiểu Unix; trên Windows cần điều chỉnh cho PowerShell hoặc `cmd`. Trong dự án Maven/Gradle, nên cấu hình compiler arguments tại build script hoặc plugin đang dùng thay vì chạy `javac` thủ công cho toàn dự án.

Hai loại cảnh báo cần phân biệt:

| Tùy chọn/cảnh báo | Trường hợp đáng chú ý | Hành động |
| --- | --- | --- |
| `-Xlint:deprecation` | Sử dụng API deprecated thông thường. | Tra Javadoc, tìm API thay thế và lên kế hoạch chuyển đổi. |
| `-Xlint:removal` | Sử dụng API đánh dấu `forRemoval = true`. | Ưu tiên thay thế, kiểm tra mốc removal đã công bố và rủi ro của release sắp tới. |
| `-Werror` | Chính sách build biến warning thành lỗi. | Phân loại cảnh báo và quyết định cách xử lý có kiểm soát; không che toàn bộ warning. |

Tùy JDK và compiler, nội dung thông báo và các cảnh báo được bật mặc định có thể khác nhau. Luôn ghi lại phiên bản compiler, flags và dependency khi so sánh kết quả migration.

### 7.2. `@SuppressWarnings` dùng như thế nào?

Trong trường hợp chưa thể sửa một lời gọi ngay lập tức, có thể giới hạn warning tại vị trí cụ thể:

```java
@SuppressWarnings("deprecation")
static String callLegacy(String id) {
    return AccountApi.getName(id);
}
```

Với API đánh dấu dự kiến loại bỏ, JDK hỗ trợ loại suppression tương ứng:

```java
@SuppressWarnings("removal")
static String callPendingRemoval(String id) {
    return AccountApi.getName(id);
}
```

Chỉ sử dụng khi đã có lý do, người chịu trách nhiệm và kế hoạch thay thế. Suppression không làm API an toàn hoặc ngăn thư viện xóa method trong release tương lai. Không đặt suppression ở phạm vi cả module chỉ để build không hiện cảnh báo.

### 7.3. Dùng `jdeprscan` đúng phạm vi

JDK cung cấp công cụ `jdeprscan` để phân tích class/JAR đã biên dịch và tìm tham chiếu đến các API Java SE deprecated thuộc release mà công cụ hỗ trợ. Ví dụ:

```bash
jdeprscan --release 11 path/to/application.jar
```

Một số bản JDK cũng hỗ trợ tùy chọn lọc các API được đánh dấu for removal; kiểm tra `jdeprscan --help` của JDK đang dùng trước khi tự động hóa. Lệnh này **không phải** bộ quét tổng quát cho mọi API deprecated của thư viện bên thứ ba. Với thư viện tự phát triển, có thể dùng compiler warnings, API diff, tìm kiếm mã nguồn và kiểm thử client.

Phân tích static chỉ bao phủ những class và tham chiếu có trong đầu vào được cung cấp. Reflection, class được nạp từ cấu hình và plugin tải lúc chạy có thể cần kiểm chứng riêng.

### 7.4. Đọc Javadoc và release notes cùng cảnh báo

Cảnh báo compiler thường chỉ chỉ ra tên API bị deprecated hoặc đánh dấu removal. Người lập trình cần mở Javadoc để biết:

- Lý do không nên dùng API cũ.
- API hoặc pattern thay thế.
- Các khác biệt contract, tham số, exception, dữ liệu và hành vi.
- Mốc phát hành bắt đầu deprecation và dự kiến removal nếu có.
- Các bước migration khi API mới không thể thay thế bằng một lời gọi tương đương.

Nếu Javadoc thiếu hướng dẫn, cần yêu cầu chủ sở hữu API bổ sung tài liệu thay vì chỉ suppress warning.

## 8. Giao tiếp lộ trình qua nhiều kênh

Annotation là một phần của giao tiếp với người tiêu thụ thư viện, nhưng người dùng không phải lúc nào cũng biên dịch lại thường xuyên. Một lộ trình deprecation cần được đưa vào các kênh mà nhóm sử dụng API thực sự theo dõi.

### 8.1. Javadoc tại điểm sử dụng

Mỗi API deprecated nên có thông tin ngắn gọn, trực tiếp tại khai báo. Nên mô tả lý do và đường chuyển đổi. Nếu khác biệt giữa API cũ và mới phức tạp, dẫn liên kết đến migration guide.

### 8.2. Release notes theo phiên bản

Khi một API chuyển trạng thái, release notes nên ghi:

- Tên API cũ, release bắt đầu deprecated và lý do.
- Tên API mới và ví dụ chuyển đổi ngắn.
- Việc `forRemoval` chuyển sang `true`, nếu có.
- Mốc removal dự kiến và phạm vi cam kết hỗ trợ; phân biệt dự kiến với quyết định chắc chắn.
- Các điểm phá tương thích khi API thực sự bị xóa hoặc thay đổi signature.

Ví dụ nội dung release notes:

> Từ thư viện 2.4, `AccountApi.getName(String)` được đánh dấu deprecated; hãy dùng `findNameById(String)`. Trong 3.0, API cũ chuyển sang `forRemoval = true`. Theo lộ trình hiện tại, dự kiến xóa ở 4.0; các client nên hoàn tất migration trước khi nâng lên 4.0.

### 8.3. Migration guide dành cho người sử dụng

Với thay đổi phức tạp, cung cấp ví dụ trước/sau:

```java
// Trước
String name = AccountApi.getName(id);

// Sau
String name = AccountApi.findNameById(id);
```

Nếu thay đổi không chỉ là rename, hướng dẫn phải giải thích rõ cách chuyển đổi dữ liệu, xử lý lỗi, cấu hình hoặc hành vi mặc định. Với hệ thống nhiều module, cung cấp bảng mapping API cũ → API mới và hướng dẫn thứ tự cập nhật dependency/client.

### 8.4. Theo dõi mức độ sử dụng API cũ

Trong kho mã nội bộ, có thể tìm lời gọi deprecated bằng compiler warning, IDE inspections, static analysis và tìm kiếm source. Với hệ sinh thái thư viện có nhiều client, nên thu thập thông tin tương thích từ các module dùng chung và phản hồi người dùng.

Không cần thêm log runtime vào mọi API deprecated; làm vậy có thể tăng chi phí vận hành, lộ dữ liệu hoặc tạo log nhiễu. Nếu cần đo usage, phải thiết kế chỉ số và giới hạn thu thập phù hợp với hệ thống.

## 9. Chính sách versioning và cam kết tương thích

`@Deprecated` không tự quy định Semantic Versioning hay lịch release. Nhóm phát triển phải công bố chính sách hỗ trợ riêng. Một số quyết định thường cần thống nhất:

- API có được giữ ít nhất một hoặc nhiều minor release sau khi deprecated không?
- Thời điểm nào một API được chuyển sang `forRemoval = true`?
- Việc loại bỏ public API có chỉ được thực hiện trong major release không?
- Có release hỗ trợ dài hạn hoặc nhánh bảo trì nào tiếp tục giữ API cũ không?
- Có module hoặc khách hàng nào cần ngoại lệ do tương thích binary không?
- Ai phê duyệt thời điểm removal và ai xác nhận số lượng client đã migration?

Với sản phẩm tuân theo SemVer, việc xóa public API thường là thay đổi phá tương thích và thường được đưa vào major release. Tuy nhiên, chính sách thực tế của dự án có thể khác; không nên suy ra mốc xóa chỉ từ `forRemoval = true`.

Khi API thuộc thư viện dùng chung, nên xây dựng **ma trận tương thích** theo phiên bản thư viện, JDK, framework và client chính. Một API thay thế có thể chỉ dùng được trên JDK mới hơn; điều đó ảnh hưởng khả năng migration của khách hàng đang ở JDK cũ. Tài liệu cần nói rõ các điều kiện tiên quyết thay vì chỉ ra lệnh “hãy đổi sang API mới”.

## 10. Những sai lầm thường gặp

### 10.1. Nhầm `since` với `@since`

`@Deprecated(since = "2.4")` ghi thời điểm API bị deprecated. Thẻ Javadoc `@since 1.0` ghi thời điểm API xuất hiện. Ghi cùng một giá trị cho hai trường khi không đúng lịch sử sẽ khiến người dùng hiểu sai vòng đời API.

### 10.2. Gắn `forRemoval = true` nhưng không có kế hoạch

`forRemoval = true` tạo tín hiệu rằng API có thể biến mất trong tương lai. Nếu không có chính sách release, replacement hoặc người chịu trách nhiệm, người dùng không biết cách hành động và có thể mất niềm tin vào cảnh báo.

### 10.3. Viết annotation mà thiếu Javadoc `@deprecated`

Annotation báo trạng thái nhưng không trả lời “thay bằng gì”. Nên có Javadoc rõ ràng, liên kết đến API mới, khác biệt hành vi và tài liệu migration.

### 10.4. Coi deprecation là removal

API deprecated vẫn có thể chạy. Ngược lại, việc xóa API mới là thay đổi cần đánh giá tương thích source và binary. Không dùng `@Deprecated` để suy ra rằng client cũ tự động chuyển được sang API mới.

### 10.5. Xóa method ngay sau khi deprecated

Client chưa kịp cập nhật có thể lỗi biên dịch hoặc gặp `NoSuchMethodError` khi dùng binary cũ. Cần xác định cửa sổ chuyển tiếp, mức độ sử dụng và release thích hợp để loại bỏ.

### 10.6. Đổi `since` mỗi lần thay trạng thái

Nếu API deprecated từ 2.4 rồi đến 3.0 mới được đánh dấu `forRemoval = true`, `since` vẫn nên phản ánh 2.4. Mốc chuyển `forRemoval` có thể được nêu trong release notes, không ghi đè lịch sử deprecation.

### 10.7. Dùng `@SuppressWarnings` để né toàn bộ công việc migration

Suppression chỉ ẩn cảnh báo ở phạm vi được áp dụng. Nó không khắc phục API sắp bị xóa. Hãy giới hạn suppression, nêu lý do và lên kế hoạch xóa suppression cùng API legacy.

### 10.8. Quên client chưa được biên dịch lại

Một library maintainer có thể không thấy cảnh báo trong chính dự án của mình nhưng vẫn có nhiều client binary dùng API cũ. Trước removal cần kiểm tra các client độc lập, plugin và hệ thống tích hợp cùng release timeline của chúng.

## 11. Quy trình dành cho người duy trì API

### Bước 1: Xác định lý do deprecate

Ghi nhận vấn đề thiết kế, bảo mật, hiệu năng hoặc nghiệp vụ khiến API cũ không còn được khuyến nghị. Xác định API thay thế có giải quyết được vấn đề và có thể sử dụng trong môi trường hỗ trợ hiện tại không.

### Bước 2: Công bố API thay thế và contract

Đảm bảo method/class mới có tài liệu, test và ví dụ. Nếu hành vi khác API cũ, mô tả rõ thay đổi, nhất là dữ liệu trả về, exception, `null`, concurrency và security.

### Bước 3: Đánh dấu deprecation bằng annotation và Javadoc

Với Java 9+:

```java
/**
 * @since 1.0
 * @deprecated Kể từ 2.4, dùng {@link #newMethod()}.
 */
@Deprecated(since = "2.4", forRemoval = false)
public void oldMethod() {
    newMethod();
}

public void newMethod() {
    // API thay thế.
}
```

Với Java 8, giữ `@Deprecated` không có thuộc tính và ghi thông tin release trong Javadoc.

### Bước 4: Phát hành thông tin chuyển đổi

Cập nhật release notes, migration guide, API reference và ví dụ client. Chỉ rõ version bắt đầu deprecation, replacement và mức độ khẩn cấp.

### Bước 5: Theo dõi client và khả năng tương thích

Biên dịch các client quan trọng với cảnh báo deprecation được bật, thống kê usage trong source và kiểm tra binary clients khi cần. Mọi thay đổi behavior trong adapter của API cũ phải có test regression.

### Bước 6: Quyết định chuyển sang `forRemoval = true`

Khi đáp ứng chính sách hỗ trợ, đổi trạng thái, cập nhật Javadoc và release notes, đồng thời thông báo thời điểm dự kiến removal. Giữ `since` là release đầu tiên đánh dấu deprecated.

### Bước 7: Loại bỏ khi đạt điều kiện

Trước khi xóa API, xác nhận release phù hợp, các client trong phạm vi hỗ trợ đã có đường chuyển đổi, công cụ phát hiện usage đã chạy và migration guide hoàn chỉnh. Sau khi xóa, kiểm tra source compatibility, binary compatibility và hành vi theo phạm vi cam kết của release mới.

## 12. Quy trình dành cho người tiêu thụ API

Khi gặp cảnh báo deprecation trong dự án nâng JDK hoặc nâng thư viện:

1. **Xác nhận API và phiên bản:** tìm method/class bị cảnh báo cùng dependency thực tế trong build.
2. **Đọc trạng thái:** xem `since`, `forRemoval`, Javadoc `@deprecated` và release notes.
3. **Đánh giá mức độ ưu tiên:** API `forRemoval = true` cần chú ý đặc biệt nếu định nâng lên release có kế hoạch xóa.
4. **Xác định replacement:** kiểm tra compatibility của API thay thế với JDK, framework và môi trường đang hỗ trợ.
5. **Sửa theo contract mới:** cập nhật source, chuyển đổi dữ liệu/cấu hình nếu cần, và giữ behavior nghiệp vụ.
6. **Kiểm thử:** chạy unit, integration và regression test cho các luồng chịu ảnh hưởng.
7. **Loại bỏ tạm thời:** khi đã migration, xóa suppression, adapter cũ không còn cần và cảnh báo liên quan.

Nếu chưa thể migration ngay, ghi nhận lý do, rủi ro, người phụ trách và deadline hợp lý; tránh việc cảnh báo tồn tại lâu nhưng không ai chịu trách nhiệm.

## 13. Mẫu ghi nhận deprecation trong tài liệu dự án

Một bảng theo dõi giúp đồng bộ mã nguồn, release notes và công việc của các nhóm client:

| Trường | Nội dung cần ghi |
| --- | --- |
| API cũ | Package, class và chữ ký method/field liên quan. |
| Introduced in | Phiên bản API lần đầu xuất hiện (`@since`). |
| Deprecated since | Phiên bản bắt đầu deprecated (`@Deprecated(since = ...)`). |
| For removal | `false` hoặc `true`, kèm phiên bản chuyển trạng thái nếu có. |
| Lý do | Vì sao API không còn được khuyến nghị. |
| API thay thế | Tên, link Javadoc và điều kiện sử dụng. |
| Khác biệt behavior | Tham số, kết quả, exception, `null`, concurrency hoặc bảo mật. |
| Removal target | Phiên bản dự kiến nếu đã được quyết định theo chính sách; ghi “chưa xác định” nếu chưa có. |
| Phạm vi client | Module, plugin, service hoặc khách hàng còn sử dụng. |
| Người phụ trách | Chủ sở hữu API và đầu mối hỗ trợ migration. |
| Bằng chứng | Build warnings, API diff, migration tests và release notes. |

Ví dụ một dòng có thể mô tả: `AccountApi.getName(String)` xuất hiện từ 1.0, deprecated từ 2.4, chuyển `forRemoval = true` trong 3.0, dự kiến xóa ở 4.0; API thay thế là `findNameById(String)`. Các mốc này phải được ghi thống nhất ở source, Javadoc và thông báo phát hành.

## 14. Checklist trước khi đánh dấu và trước khi loại bỏ API

**Khi bắt đầu deprecated:**

- [ ] Đã mô tả rõ lý do không khuyến nghị API cũ.
- [ ] Đã có API hoặc phương án thay thế khả thi.
- [ ] Đã chọn đúng phiên bản cho `since` của annotation.
- [ ] Đã phân biệt `@since` (giới thiệu API) với `@deprecated` (hướng dẫn thay thế).
- [ ] Đã xác nhận source level hỗ trợ thuộc tính `since` và `forRemoval` nếu sử dụng.
- [ ] Đã bổ sung Javadoc, ví dụ migration và release notes.
- [ ] Đã kiểm thử adapter nếu giữ method cũ chuyển tiếp sang API mới.

**Khi chuẩn bị `forRemoval = true` hoặc removal:**

- [ ] Đã có chính sách thời gian hỗ trợ và mốc phát hành dự kiến.
- [ ] Đã đánh giá client source và binary còn phụ thuộc.
- [ ] Đã xác nhận khả năng sử dụng API thay thế trên JDK và framework được hỗ trợ.
- [ ] Đã thông báo thay đổi trạng thái và hướng dẫn migration.
- [ ] Đã giữ nguyên `since` của lần deprecation đầu tiên.
- [ ] Đã kiểm tra source/binary compatibility theo cam kết sản phẩm.
- [ ] Đã xác định cách xử lý ngoại lệ hoặc trì hoãn nếu client quan trọng chưa thể nâng.

## 15. Kết luận thực hành

`@Deprecated` là một tín hiệu kỹ thuật cho thấy API không còn được khuyến nghị. `since` lưu lại release bắt đầu deprecation, còn `forRemoval` cho biết tác giả có ý định loại bỏ API trong tương lai. `@since` và `@deprecated` trong Javadoc bổ sung lịch sử ra đời và hướng dẫn chuyển đổi mà annotation không tự diễn đạt được.

Trong Java compatibility migration, hãy coi deprecation là một **hợp đồng truyền thông và tương thích qua nhiều release**: công bố API thay thế, giữ khoảng chuyển tiếp phù hợp, hướng dẫn client, theo dõi cảnh báo và chỉ xóa API khi các điều kiện hỗ trợ cho phép. Khi code, Javadoc, release notes và kiểm thử nói cùng một lộ trình, người sử dụng thư viện có thể chủ động nâng cấp trước khi thay đổi phá tương thích xảy ra.
