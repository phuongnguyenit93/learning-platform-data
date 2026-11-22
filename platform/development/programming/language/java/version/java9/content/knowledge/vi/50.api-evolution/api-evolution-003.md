# Thông tin thay thế trong tài liệu @deprecated: hướng dẫn chuyển đổi API (Java 9+)

## 1. Mục tiêu

Khi một API Java không còn là lựa chọn được khuyến nghị, tác giả thư viện cần giúp người dùng **biết chính xác nên dùng API nào thay thế, từ phiên bản nào, khác biệt hành vi là gì và khi nào cần chuyển đổi**. Java cung cấp hai cơ chế bổ trợ:

- Annotation `@Deprecated` để đánh dấu phần tử API cho công cụ biên dịch, IDE và công cụ phân tích.
- **Javadoc block tag** `@deprecated` (chữ **d** thường) để đưa **lý do và hướng dẫn thay thế** vào tài liệu HTML sinh từ mã nguồn.

Từ Java 9, annotation có hai thuộc tính `since` và `forRemoval`. Chúng vẫn là cách biểu đạt trạng thái deprecation trong Java hiện đại. Bài này sử dụng JDK 17+ để minh họa; các ví dụ đã được kiểm tra bằng JDK 24. Trọng tâm là **cách viết tài liệu chuyển đổi cho code hiện đang được bảo trì**, không đi sâu vào các kỹ thuật hoặc API lỗi thời.

Sau bài học, bạn có thể:

1. Phân biệt annotation `@Deprecated`, Javadoc `@deprecated`, `@since` và liên kết `{@link}`.
2. Viết một thông báo deprecation có **phiên bản, API thay thế và hành động cụ thể**.
3. Dùng `@Deprecated(since = "…", forRemoval = …)` phù hợp với kế hoạch thư viện.
4. Tạo liên kết trực tiếp từ phương thức cũ đến phương thức mới trong trang Javadoc.
5. Kiểm tra cảnh báo của `javac` và trang `deprecated-list.html` của Standard Doclet.
6. Hướng dẫn di chuyển khi API mới không tương đương hoàn toàn về tham số, kết quả hoặc hành vi.
7. Đặt ra quy trình deprecation nhất quán mà không vô tình phá vỡ người dùng hiện tại.

## 2. Khái niệm: deprecation không đồng nghĩa với xóa API

**Deprecated** có nghĩa phần tử API vẫn có thể tồn tại và hoạt động, nhưng **không còn được khuyến nghị cho mã mới**. Có thể vì một tên khó hiểu, một thiết kế được cải thiện, lỗi API không thể sửa mà vẫn giữ tương thích, hoặc yêu cầu thay đổi hành vi/bảo mật.

Một vòng đời thường gặp:

```text
API hiện hành
    |
    | xuất hiện API thay thế phù hợp
    v
API cũ được đánh dấu @Deprecated + có hướng dẫn trong @deprecated
    |
    | người dùng sửa code, test và triển khai lại
    v
Người dùng chuyển sang API mới
    |
    | nếu thư viện đã công bố kế hoạch loại bỏ
    v
API cũ có thể bị xóa ở một phiên bản tương lai
```

Không phải API deprecated nào cũng được lên lịch xóa. Annotation `forRemoval=false` (mặc định) biểu đạt **không có ý định loại bỏ hiện tại**, còn `forRemoval=true` biểu đạt **API được dự kiến/đang xem xét loại bỏ ở phiên bản tương lai**. Cả hai vẫn cần hướng dẫn thay thế đầy đủ.

**Đánh dấu deprecated không tự làm phương thức ngừng chạy**. Nếu source hoặc binary vẫn còn phương thức, lời gọi có thể tiếp tục chạy; công cụ phát cảnh báo và tài liệu thông báo nguy cơ. Không được tự suy ra “ngày xóa” chỉ từ `since`.

## 3. Annotation và Javadoc tag: hai nhiệm vụ khác nhau

| Cú pháp | Đặt ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `@Deprecated` | Trực tiếp trước khai báo Java | Metadata cho compiler/IDE/tooling biết không nên dùng phần tử |
| `@Deprecated(since = "2.1", forRemoval = false)` | Trước khai báo | Biết phiên bản thư viện bắt đầu deprecate và trạng thái có kế hoạch loại bỏ |
| `@deprecated Kể từ 2.1, dùng {@link #findByCode(String)}.` | Trong comment `/** ... */` ngay trước khai báo | Giải thích cho con người cách thay thế, có liên kết nhảy tới API mới |
| `@since 1.0` | Trong comment Javadoc | Phiên bản API **được giới thiệu**, không phải thời điểm bị deprecated |
| `{@link #findByCode(String)}` | Inline trong Javadoc | Liên kết đến phương thức thay thế cùng class |
| `@see #findByCode(String)` | Trong comment Javadoc | Thêm tham chiếu liên quan ở mục See Also; có thể dùng bổ trợ |

Trong Java hiện đại, **nên cung cấp cả annotation và Javadoc tag**: annotation đánh dấu trạng thái cho compiler, còn tag cung cấp giải pháp thực tế cho người dùng. Không chỉ đưa chữ “Deprecated” vào phần mô tả thông thường rồi mong IDE hiểu đây là API bị deprecated.

Đừng nhầm **chữ hoa/chữ thường**:

```java
/**
 * @deprecated Kể từ 2.1, dùng {@link #findByCode(String)}.
 */
@Deprecated(since = "2.1", forRemoval = false)
public static String lookup(String code) {
    return findByCode(code);
}
```

Đây là **đoạn minh họa**, giả định class đã có phương thức `findByCode(String)`. Mã hoàn chỉnh và có thể biên dịch nằm ở mục 6.

- `@deprecated`: block tag viết trong comment Javadoc, không phải annotation.
- `@Deprecated`: annotation của Java, không phải tag trong comment.
- `{@link #findByCode(String)}`: inline tag giải quyết liên kết đến phương thức thay thế thực sự.

Một số trường hợp Javadoc comment theo cú pháp truyền thống từng được nhận diện deprecated khi chỉ có `@deprecated`, nhưng **không dùng cách đó làm quy tắc cho mã mới**. Cú pháp Markdown Javadoc hiện đại cũng yêu cầu annotation để đánh dấu phần tử bị deprecated. Vì vậy hãy luôn thống nhất cả hai nguồn thông tin.

## 4. Hiểu đúng `since`, `forRemoval` và `@since`

### 4.1. `@Deprecated.since` — bắt đầu bị deprecated

```java
@Deprecated(since = "2.1", forRemoval = false)
```

`since = "2.1"` là **chuỗi phiên bản mà thư viện công bố trạng thái deprecated**. Với thư viện tự phát triển, đó thường là version của **thư viện**, không mặc nhiên là phiên bản Java runtime. Nếu bạn bảo trì chính một API JDK, số này thường là version của JDK.

Giá trị `since` chỉ mang tính **thông tin**: compiler không tự so sánh nó với dependency version để quyết định xóa hoặc chặn lời gọi. Có thể đặt chuỗi phiên bản theo chính sách phát hành, ví dụ `"2.1"`, `"3.0"`; nên dùng một quy ước thống nhất.

### 4.2. `@Deprecated.forRemoval` — có kế hoạch loại bỏ hay không

| Giá trị | Diễn giải phù hợp | Hệ quả cần nghĩ tới |
| --- | --- | --- |
| `forRemoval = false` | Không nên sử dụng trong mã mới; hiện chưa có chủ trương loại bỏ | Người dùng nên chuyển đổi theo hướng dẫn; API cũ có thể được giữ để tương thích |
| `forRemoval = true` | Phần tử được xác định là đối tượng **có thể bị xóa** ở phiên bản tương lai | Người dùng cần ưu tiên di chuyển hơn; build có thể xuất cảnh báo riêng về removal |

**Không đặt `forRemoval = true` chỉ để tạo cảnh báo “mạnh” hơn** nếu thư viện không có kế hoạch loại bỏ tương ứng. Ngược lại, `false` không phải hợp đồng đảm bảo API được duy trì mãi mãi.

Compiler cung cấp cảnh báo cho deprecation và deprecation-for-removal; `-Xlint:deprecation` và `-Xlint:removal` giúp kiểm tra hai nhóm cảnh báo khi biên dịch. Nếu dự án dùng `-Werror`, cần có quy trình di chuyển trước khi cảnh báo làm build thất bại.

### 4.3. `@since` — thời điểm xuất hiện API

`@since` trong Javadoc có ý nghĩa khác `@Deprecated.since`:

```java
/**
 * Tra cứu theo mã sản phẩm.
 * @since 2.1
 */
public static String findByCode(String code) {
    return "item:" + code;
}
```

Đây là đoạn minh họa cần bổ sung `@param`/`@return` khi sinh tài liệu với quy tắc doclint cho method. `@since 2.1` ở đây nghĩa là **phương thức mới có từ version 2.1**; không phải nó bị deprecated. Ngược lại `@Deprecated(since="2.1")` ở phương thức cũ nghĩa là **phương thức cũ bị đánh dấu từ 2.1**.

Khi viết hướng dẫn migration, cần cho người dùng biết **phiên bản thư viện tối thiểu cung cấp API thay thế**, đặc biệt nếu họ chưa nâng dependency.

## 5. Viết nội dung `@deprecated` sao cho có thể hành động

Theo hướng dẫn của Standard Doclet, **câu đầu tiên của đoạn `@deprecated` nên nêu từ khi bị deprecated và dùng gì thay thế**. Câu đầu thường được đưa vào phần tóm tắt và danh sách deprecated API. Các câu sau có thể nêu lý do và khác biệt hành vi.

Một thông báo có ích trả lời được các câu hỏi:

- **Khi nào?** Ví dụ “Kể từ 2.1”.
- **Thay bằng gì?** Nêu chính xác class/method/signature, ưu tiên `{@link}` để bấm được.
- **Làm thế nào?** Nếu API cũ và mới khác tham số hoặc return type, kèm quy tắc chuyển đổi.
- **Vì sao?** Giải thích ngắn gọn nếu giúp người dùng tránh lặp lại lỗi thiết kế.
- **Có rủi ro gì?** Nếu semantics, exception, timezone, null handling, thread safety hay hợp đồng bảo mật thay đổi, phải nói rõ.
- **Mốc loại bỏ?** Chỉ nêu khi có cam kết/kế hoạch phiên bản chính thức; không tự suy diễn từ `forRemoval`.

Ví dụ một thông báo hữu ích:

```java
/**
 * Tra cứu bằng tên phương thức trước đây.
 *
 * @param code mã mặt hàng
 * @return chuỗi kết quả thử nghiệm
 * @deprecated Kể từ 2.1, dùng {@link #findByCode(String)}.
 *             Phương thức này tạm thời chuyển tiếp sang API thay thế.
 */
@Deprecated(since = "2.1", forRemoval = false)
public static String lookup(String code) {
    return findByCode(code);
}
```

Ở đây nội dung đầu tiên chỉ đúng **phiên bản và mục tiêu thay thế**. Đường dẫn `{@link #findByCode(String)}` trỏ đến phương thức cùng class với tham số kiểu `String`; Doclet giải quyết kiểu tham số ở thời điểm sinh HTML.

### 5.1. Liên kết tới API khác class

Nếu phương thức mới nằm ở class khác, dùng tên đủ rõ để Doclet giải quyết, ví dụ:

```java
/**
 * @deprecated Kể từ 3.0, xem
 *             {@link com.example.api.ProductCatalog#findByCode(String)}.
 */
```

Đây là **đoạn Javadoc minh họa**, cần gắn vào một khai báo Java hợp lệ. Nếu type nằm ở module khác, phải có dependency phù hợp để `javadoc` giải quyết liên kết; nếu tài liệu mục tiêu bên ngoài bộ doc hiện tại, có thể dùng cấu hình liên kết tài liệu API ngoài (`-link`) theo build của dự án. Đừng chỉ gõ tên phương thức như text nếu có thể tạo liên kết kiểm chứng được.

### 5.2. Khi không có replacement một-một

Không bịa ra một phương thức thay thế nếu thật sự chưa có. Thay vì viết “Use new API” chung chung, hãy mô tả:

- Cách làm mới phù hợp với các nhu cầu còn được hỗ trợ.
- Những trường hợp không còn được hỗ trợ, và lý do.
- Nếu cần nhiều bước, thứ tự gọi, dữ liệu cần chuyển đổi và điều kiện về phiên bản thư viện.
- Trang migration guide ổn định hoặc tài liệu kiến trúc giải thích chi tiết.

Ví dụ câu phù hợp trong `@deprecated` khi không có phương thức thay thế tương đương:

> Kể từ 3.0, API đồng bộ này không còn được khuyến nghị; dùng quy trình bất đồng bộ được mô tả trong hướng dẫn nâng cấp phiên bản 3.0. Không có phương thức thay thế tương đương một-một.

Câu trên là **mẫu diễn đạt**, không phải mô tả một API thật.

## 6. Ví dụ Java 17+ đầy đủ: phương thức cũ và phương thức thay thế

Ví dụ này có hai file Java, biên dịch và chạy được. Một API tra cứu có phương thức mới `findByCode`; phương thức `lookup` được giữ làm wrapper chuyển tiếp để người dùng có thời gian di chuyển. Đây là một mô hình thích hợp khi **hai phương thức thực sự có cùng hành vi**.

### 6.1. Cấu trúc thư mục

```text
api-deprecation-demo/
└── src/
    └── com/
        └── example/
            ├── api/
            │   └── ProductCatalog.java
            └── app/
                └── Demo.java
```

### 6.2. `src/com/example/api/ProductCatalog.java`

```java
package com.example.api;

/**
 * API tra cứu hàng hóa theo mã.
 *
 * @since 1.0
 */
public final class ProductCatalog {
    private ProductCatalog() {}

    /**
     * Tra cứu mặt hàng bằng mã.
     *
     * @param code mã mặt hàng
     * @return chuỗi kết quả thử nghiệm
     * @since 2.1
     */
    public static String findByCode(String code) {
        return "item:" + code;
    }

    /**
     * Tra cứu bằng tên phương thức trước đây.
     *
     * @param code mã mặt hàng
     * @return chuỗi kết quả thử nghiệm
     * @deprecated Kể từ 2.1, dùng {@link #findByCode(String)}.
     *             Phương thức này tạm thời chuyển tiếp sang API thay thế.
     */
    @Deprecated(since = "2.1", forRemoval = false)
    public static String lookup(String code) {
        return findByCode(code);
    }
}
```

Lưu ý về hai dòng version:

- `@since 1.0` ở class nói class có từ bản 1.0.
- `@since 2.1` ở `findByCode` nói API thay thế bắt đầu có ở 2.1.
- `@Deprecated(since="2.1")` trên `lookup` nói phương thức đó bị deprecated từ 2.1.
- `@deprecated Kể từ 2.1, dùng...` giải thích bằng ngôn ngữ người đọc và tạo liên kết thật.

Annotation đặt **giữa comment tài liệu và declaration**; compiler nhìn thấy metadata, Doclet nhìn thấy cả annotation và tag. Phần thân `lookup` gọi `findByCode` nên bảo đảm cùng kết quả trong ví dụ. Với API thật, chỉ dùng wrapper khi có thể duy trì hành vi cũ một cách an toàn.

### 6.3. `src/com/example/app/Demo.java`

```java
package com.example.app;

import com.example.api.ProductCatalog;

public class Demo {
    public static void main(String[] args) {
        String current = ProductCatalog.findByCode("A-12");
        String previous = ProductCatalog.lookup("A-12");
        System.out.println("current=" + current);
        System.out.println("previous=" + previous);
        System.out.println("equal=" + current.equals(previous));
    }
}
```

`Demo` gọi phương thức cũ **có chủ đích** để trình diễn compiler warning. Mã ứng dụng thực tế nên gọi `findByCode`; không nên giữ lời gọi `lookup` sau khi di chuyển xong.

### 6.4. Biên dịch, chạy và tạo Javadoc

Từ thư mục gốc `api-deprecation-demo`:

```bash
javac -encoding UTF-8 -Xlint:deprecation -d classes src/com/example/api/ProductCatalog.java src/com/example/app/Demo.java
java -cp classes com.example.app.Demo
javadoc -quiet -Xdoclint:all -encoding UTF-8 -charset UTF-8 -d docs src/com/example/api/ProductCatalog.java
```

Lệnh `javac` thành công và phát sinh **một warning** do `Demo` gọi API đã deprecated. Phần thông báo chính, không tính path và vị trí source (phụ thuộc máy):

```text
warning: [deprecation] lookup(String) in ProductCatalog has been deprecated
1 warning
```

**Stdout chính xác của `java`:**

```text
current=item:A-12
previous=item:A-12
equal=true
```

Lệnh `javadoc` tạo HTML thành công, exit code 0 trên JDK 24 với `-Xdoclint:all`. Thư mục output bao gồm:

```text
docs/
├── index.html
├── deprecated-list.html
└── com/
    └── example/
        └── api/
            └── ProductCatalog.html
```

Trong `deprecated-list.html` có `ProductCatalog.lookup(String)` và phần hướng dẫn đi sang `findByCode(String)`; trang `ProductCatalog.html` đánh dấu phương thức `lookup` là Deprecated và chứa liên kết từ `{@link}` trỏ tới method hiện hành. Không cần và không nên sửa HTML đã sinh ra; nguồn sự thật là comment Javadoc và annotation.

**Giới hạn của kết quả thử nghiệm:** Warning có thể chứa tên file, số dòng và cách diễn đạt khác giữa các JDK/compiler; chỉ đoạn stdout của chương trình Java là dữ liệu cố định ở ví dụ này. Vị trí/tổ chức các tệp HTML chi tiết cũng có thể thay đổi theo phiên bản doclet.

## 7. Javadoc hiển thị thông tin deprecation như thế nào?

Với Standard Doclet hiện đại, khi một phần tử được đánh dấu `@Deprecated`:

1. Trang class chứa mục hoặc nhãn **Deprecated** cho phần tử tương ứng.
2. Nội dung `@deprecated` được đưa tới phần giải thích deprecation nổi bật trước mô tả chính của phần tử.
3. Câu đầu của nội dung deprecation có thể được hiển thị trong summary và danh sách.
4. Trang **`deprecated-list.html`** liệt kê các API bị deprecated của bộ tài liệu đang sinh.
5. `{@link}` được chuyển thành đường dẫn tới khai báo thay thế mà Doclet có thể phân giải.

Khi `forRemoval=true`, thông tin tài liệu có thể nêu trạng thái “for removal”, giúp phân biệt mức cảnh báo với trường hợp không có ý định loại bỏ ngay. Đây là metadata về ý định, **không** phải lịch tự động xóa.

### 7.1. Kiểm tra bằng tay

Sau khi chạy lệnh ở mục 6:

- Mở `docs/index.html` trong trình duyệt và tìm mục **Deprecated** ở thanh điều hướng.
- Mở `docs/deprecated-list.html`, tìm `lookup(String)`.
- Nhấp tên phần tử để đến trang `ProductCatalog` và phần deprecated tương ứng.
- Nhấp liên kết `findByCode(String)` trong phần mô tả; xác nhận đến đúng phương thức mới.
- Kiểm tra thông điệp cho biết **“kể từ 2.1”** và vì sao wrapper vẫn còn.
- Đảm bảo phương thức `findByCode` **không** bị đánh dấu deprecated.

Đừng đánh giá tài liệu chỉ bằng việc trang `deprecated-list.html` có tồn tại. Một trang index vẫn có thể tồn tại nhưng **không chứa mục mong đợi** nếu phương thức không thuộc tập API được xuất ra hoặc annotation/comment đặt sai vị trí.

### 7.2. Khi javadoc sinh tài liệu cho module

Nếu thư viện dùng Java modules (`module-info.java`), quy trình tương tự: khai báo class và member bình thường trong module, rồi dùng `javadoc --module-source-path ... --module ...` để sinh tài liệu. Phần tử muốn deprecate vẫn phải có annotation và comment thích hợp. Tài liệu sinh chỉ bao gồm phần API mà build đã chọn, nên nhớ kiểm tra module/package đúng phạm vi.

Nội dung deprecation được đặt **tại khai báo cần chuyển đổi**; chỉ gắn ghi chú ở trang module tổng quan là chưa đủ để compiler báo warning khi người dùng gọi member cụ thể.

## 8. Migration khi API mới có hành vi khác

Trong ví dụ ở mục 6, hai phương thức trả cùng giá trị, nhưng nhiều dự án thực tế có sự thay đổi hợp đồng. Khi đó một lời khuyên “đổi tên phương thức” là thiếu.

| Loại thay đổi | Thông tin cần viết vào `@deprecated`/migration guide | Kiểm thử người dùng cần chạy |
| --- | --- | --- |
| Đổi tên, cùng tham số và hành vi | Chỉ ra `{@link}` tới phương thức mới, xác nhận tương đương | So sánh input/output, exception |
| Đổi kiểu tham số | Nêu cách chuyển đổi dữ liệu và quy tắc null/default | Ca biên, null, validation |
| Đổi return type | Chỉ ra cách lấy lại dữ liệu cần thiết, xử lý trạng thái lỗi | Kiểm thử conversion và xử lý lỗi |
| Đổi checked exception | Nêu các exception mới hoặc không còn, thời điểm phát sinh | Ca thành công và ca lỗi |
| Đổi thread model hoặc chuyển sang bất đồng bộ | Nêu cơ chế gọi, await/callback, lifecycle | Đồng thời, hủy tác vụ, timeout |
| Đổi timezone/charset/đơn vị | Nêu chính xác đơn vị và cách chuyển đổi | Input Unicode, múi giờ, tính chính xác |
| Thay đổi bảo mật | Lý do bỏ API cũ, cách cấu hình an toàn mới | Test bảo mật và tương thích |
| Không có thay thế tương đương | Nêu hành vi không còn hỗ trợ và hướng triển khai thay thế | Test chức năng nghiệp vụ thay thế |

Một deprecation có giá trị là **một hướng dẫn hành động**, không chỉ là nhãn cảnh báo. Nếu quá nhiều thay đổi không thể giải thích ngay trong một tag, đặt một đoạn ngắn có `{@link}` đến API tiếp nhận và dẫn tới migration guide có phiên bản, rồi duy trì URL ổn định.

### 8.1. Ví dụ cách diễn đạt khi thay đổi semantics

Tình huống giả định: phương thức cũ nhận khoảng thời gian bằng một `long` nhưng không nói rõ đơn vị; phương thức mới nhận `Duration`. Một hướng dẫn nên ghi:

> Kể từ 3.0, dùng phương thức mới nhận `Duration`; chuyển giá trị cũ (mili giây) bằng `Duration.ofMillis(...)`. Giá trị âm bị từ chối ở API mới.

Đây là **ví dụ hướng dẫn viết tài liệu**, không phải mô tả API Java chuẩn. Nó cho người dùng thông tin quan trọng về đơn vị và hành vi, thay vì chỉ nêu tên phương thức.

### 8.2. Đánh dấu trước khi xóa

Một quy trình phát hành có thể áp dụng:

1. Cung cấp API thay thế đã ổn định, có test, tài liệu và khả năng dùng trên bản thư viện mục tiêu.
2. Đánh dấu API cũ bằng cả `@Deprecated` và `@deprecated`, chỉ rõ version và mục tiêu chuyển đổi.
3. Giữ wrapper/adapter khi cần và khi duy trì được an toàn, hoặc hướng dẫn trực tiếp nếu semantics đã khác.
4. Chạy CI với `-Xlint:deprecation` để phát hiện nơi thư viện/app vẫn gọi API cũ.
5. Truyền thông ý định loại bỏ thật sự trước khi đánh dấu `forRemoval=true`; nêu mốc phiên bản nếu đã có chính sách.
6. Chỉ xóa API theo quy trình tương thích và versioning của dự án, kèm thông tin nâng cấp.

Không tự suy ra một API deprecated có thể bị xóa an toàn chỉ vì unit test của thư viện đã pass. Cần xét cả thư viện bên thứ ba, người dùng chưa nâng cấp và ràng buộc binary/source compatibility.

## 9. Compiler warning: phát hiện và xử lý hợp lý

### 9.1. `-Xlint:deprecation`

Dùng để hiển thị chi tiết cảnh báo khi mã gọi phần tử đã deprecated:

```bash
javac -Xlint:deprecation -encoding UTF-8 -d classes src/com/example/api/ProductCatalog.java src/com/example/app/Demo.java
```

Trong ví dụ trên, warning nằm ở `Demo.java` vì class này **sử dụng** `lookup(String)` từ class khác. Compiler không tự đổi lời gọi sang `findByCode`; người phát triển phải cập nhật mã và chạy test.

### 9.2. `-Xlint:removal`

Khi `@Deprecated(forRemoval = true)` được dùng có chủ đích, compiler có thể phát warning thuộc nhóm **removal**. Nhóm cảnh báo này cần được ưu tiên đánh giá sớm vì API có thể không còn tồn tại sau một lần nâng version.

Tuy nhiên, ý định loại bỏ ở annotation **không cho biết cụ thể phiên bản nào sẽ xóa**. Muốn quản lý chính xác, cần release note hoặc migration guide riêng của thư viện.

### 9.3. Không lạm dụng `@SuppressWarnings`

Java cho phép ức chế cảnh báo deprecation ở đoạn code đã phân tích và chấp nhận rủi ro:

```java
@SuppressWarnings("deprecation")
static String temporaryAdapter(String code) {
    return ProductCatalog.lookup(code);
}
```

Đây là **đoạn minh họa**, giả sử đã import `ProductCatalog` và method nằm trong một class hợp lệ. Cách này chỉ **ẩn cảnh báo**, không sửa vấn đề tương thích hoặc biến API cũ thành lựa chọn được khuyến nghị. Khi cần dùng tạm trong một adapter, ghi rõ lý do, ngày/phiên bản dự kiến bỏ và có test. Không đặt `@SuppressWarnings("deprecation")` trên cả project chỉ để build “xanh”.

Đối với cảnh báo loại bỏ, khóa suppress liên quan là `"removal"`; ẩn cảnh báo vẫn không bảo đảm API tồn tại trong bản runtime/libraries tương lai.

## 10. Kiểm thử tài liệu trong CI

Để tránh deprecation chỉ đúng trên giấy, nên kiểm tra:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Java source compile | API mới và API cũ (nếu còn được hỗ trợ) đều biên dịch, không lỗi |
| `javac -Xlint:deprecation` cho client mô phỏng | Có warning khi gọi phương thức cũ; khi đổi sang mới warning biến mất |
| `javadoc -Xdoclint:all` | HTML được sinh thành công, không báo lỗi liên kết/cú pháp |
| Trang `deprecated-list.html` | Phương thức cũ xuất hiện đúng tên và signature |
| Liên kết `{@link}` | Bấm được và đi đến API thay thế thực sự |
| Ký hiệu `since` và trạng thái removal | Khớp release policy của thư viện |
| API thay thế | Có `@param`, `@return`, `@throws` (nếu có) và giải thích đủ để triển khai |
| API cũ được giữ tạm | Adapter đúng hành vi đã cam kết, có test chuyển đổi |
| Client đã di chuyển | Không còn warning deprecation ngoài vùng adapter đã xét |
| Tài liệu nhiều module | Module/package cần xuất có trong scope build Javadoc |

Đừng cố snapshot nguyên HTML giữa hai phiên bản JDK. Standard Doclet có thể thay đổi cấu trúc CSS/HTML mà nội dung vẫn chính xác. Kiểm tra phần tử có xuất hiện hay không, thông điệp đúng và liên kết dẫn đến đúng API là những tiêu chí có giá trị hơn.

Khi tài liệu có nhiều ngôn ngữ, nhớ dùng UTF-8 cho mã nguồn và output HTML. Chuỗi tiếng Việt trong `@deprecated` phải hiển thị đủ dấu, đồng thời link đến Java identifier phải giải quyết đúng tên type và signature.

## 11. Lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chỉ thêm `@Deprecated`, không có `@deprecated` | Người dùng thấy warning nhưng không biết nên làm gì | Thêm câu đầu nêu phiên bản và `{@link}` tới replacement |
| Chỉ thêm `@deprecated` và bỏ annotation | Metadata cho compiler/IDE không nhất quán; đặc biệt không phù hợp với Markdown Javadoc hiện đại | Dùng annotation và tag cùng nhau |
| Nhầm `@since` với `@Deprecated.since` | Ghi sai lịch sử API | `@since` = xuất hiện; annotation since = bắt đầu deprecated |
| Viết “Use new API” | Người đọc không biết method/signature cụ thể | Tạo `{@link #newMethod(String)}` hoặc hướng dẫn chuyển đổi chính xác |
| Link tới method không tồn tại/không trong classpath Javadoc | Doclet báo lỗi hoặc link hỏng | Kiểm tra signature, module dependency và cấu hình javadoc |
| Đặt `forRemoval=true` dù chưa có ý định xóa | Gây báo động sai và chi phí migration không cần thiết | Gắn trạng thái removal theo release policy |
| Dùng `forRemoval=false` như lời hứa giữ vĩnh viễn | Người dùng hiểu sai kỳ vọng tương thích | Nêu rõ chính sách versioning/release ngoài annotation |
| Di chuyển bằng cách đổi tên thuần túy khi semantics khác | Bug về null, thời gian, exception, đơn vị hoặc bảo mật | Viết mapping và test đầy đủ |
| Chỉ sửa HTML đã sinh | Build sau ghi đè, thông tin không nằm trong source | Sửa comment và annotation trong source, chạy lại javadoc |
| Đánh dấu API mới deprecated do copy/paste | Người dùng không còn đường migration rõ ràng | Xác minh annotation/tag được đặt đúng phần tử |
| Dùng `@SuppressWarnings` trên diện rộng | Che các nơi cần chuyển đổi | Chỉ ức chế hẹp có lý do, tiếp tục triển khai migration |
| Xóa API ngay trong bản phát hành sau mà không báo | Phá source/binary compatibility cho người dùng | Có quy trình deprecation, changelog, compatibility và release policy |

## 12. Bài tập thực hành

1. Tạo hai file ở mục 6 và chạy lệnh `javac`, `java`, `javadoc`. Xác nhận warning của `lookup`, stdout của `Demo` và trang `deprecated-list.html`.
2. Sửa `Demo` chỉ gọi `findByCode` rồi biên dịch lại. Warning deprecation của lời gọi cũ phải biến mất.
3. Trên trang Javadoc, nhấp liên kết từ `lookup` đến `findByCode`. Nếu không đến đúng nơi, kiểm tra signature trong `{@link}`.
4. Đổi thử chuỗi `@Deprecated(since = "2.2", forRemoval = false)` trong một bản thử nghiệm; cập nhật văn bản `@deprecated` tương ứng và giải thích tại sao hai nơi phải nhất quán.
5. Đề xuất cách viết thông báo khi replacement nhận tham số khác hoặc có exception mới. Bổ sung một đoạn migration trước/sau phù hợp.
6. Xây dựng checklist review để bảo đảm việc đánh dấu deprecated trong source, Javadoc, release notes và CI không mâu thuẫn.

Không áp dụng `forRemoval=true` trên API của dự án thật chỉ để thực hành; dùng bản thử nghiệm độc lập và tuân thủ chính sách phát hành khi quyết định trạng thái này.

## 13. Câu hỏi ôn tập

**1.** `@Deprecated(since = "2.1")` và `@since 2.1` có giống nhau không?

**2.** Trong `@deprecated`, câu đầu tiên nên có tối thiểu thông tin gì?

**3.** Vì sao nên dùng `{@link #findByCode(String)}` thay cho việc chỉ viết tên method bằng chữ?

**4.** `forRemoval=true` có nghĩa compiler tự xóa phương thức ở version 2.2 không?

**5.** Nếu phương thức mới có thứ tự tham số khác, chỉ viết “use newMethod” đã đủ chưa?

**6.** Người dùng vẫn gọi được API cũ và chương trình chạy đúng. Tại sao vẫn cần migration?

**Gợi ý đáp án:** (1) Không: `@Deprecated.since` cho thời điểm bắt đầu deprecation, `@since` cho thời điểm xuất hiện; (2) phiên bản deprecation và replacement; (3) liên kết được Doclet kiểm tra/nhảy tới khai báo cụ thể; (4) không, chỉ biểu thị API có thể bị loại bỏ ở bản tương lai; (5) chưa, phải mô tả mapping và khác biệt semantics; (6) tránh cảnh báo tích lũy, cải thiện thiết kế và giảm rủi ro tương thích hoặc loại bỏ về sau.

## 14. Tài liệu tham khảo chính thức

- [Oracle JDK 25 — Documentation Comment Specification: @deprecated](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html)
- [Oracle JDK 25 — How to Deprecate APIs (Core Libraries Developer Guide)](https://docs.oracle.com/en/java/javase/25/core/java-core-libraries-developer-guide.pdf)
- [Oracle Java SE 25 API — Deprecated annotation](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Deprecated.html)
- [Oracle JDK 25 — javadoc command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html)
- [Oracle JDK 25 — javac command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)

Một thông báo `@deprecated` tốt giúp người đọc **chuyển đổi được**, chứ không chỉ biết API cũ “không nên dùng”. Hãy duy trì annotation đúng trạng thái, câu đầu tiên nêu phiên bản và replacement, liên kết Javadoc kiểm chứng được, và một hợp đồng migration rõ ràng khi hành vi mới khác hành vi trước đây.