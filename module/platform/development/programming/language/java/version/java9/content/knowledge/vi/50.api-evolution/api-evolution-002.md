# Phân biệt cảnh báo deprecated với cảnh báo removal trong Java 9+

## 1. Hai loại cảnh báo cùng nói “API không nên tiếp tục dùng”, nhưng mức độ khác nhau

Khi một API Java bị đánh dấu **deprecated**, lập trình viên được cảnh báo rằng nên chuyển sang cách dùng khác. Từ **Java 9** (JEP 277 — Enhanced Deprecation), Java phân biệt rõ **hai dạng** dựa trên thuộc tính `forRemoval` của annotation `@Deprecated`:

| Tiêu chí | Ordinary deprecation — `[deprecation]` | Terminal deprecation — `[removal]` |
|---|---|---|
| Đánh dấu | `@Deprecated` hoặc `@Deprecated(forRemoval=false)` | `@Deprecated(forRemoval=true)` |
| Ý nghĩa | Việc sử dụng API không còn được khuyến khích; tại thời điểm đánh dấu **chưa có chủ đích cụ thể loại bỏ** API | API **được dự định loại bỏ** trong một phiên bản tương lai |
| Loại cảnh báo của `javac` | Cảnh báo deprecation thông thường | Cảnh báo removal |
| Lint tương ứng | `-Xlint:deprecation` | `-Xlint:removal` |
| Mặc định thường thấy của `javac` | Có thể chỉ hiện dòng **Note** tóm tắt, chưa liệt kê từng chỗ dùng | `removal` được bật mặc định; thường thấy cảnh báo chi tiết |
| Chặn cục bộ | `@SuppressWarnings("deprecation")` | `@SuppressWarnings("removal")` |
| Ưu tiên xử lý | Lập kế hoạch thay thế; đánh giá tác động và tài liệu chuyển đổi | Ưu tiên xử lý cao hơn trước khi nâng JDK hoặc nâng phiên bản thư viện |

**Điểm mấu chốt:** Cả hai đều là **cảnh báo biên dịch**, **không tự động là lỗi biên dịch**. Sự tồn tại của `[removal]` không có nghĩa phương thức đã bị xóa ở phiên bản đang dùng. Ngược lại, một API `forRemoval=false` vẫn có thể được thay đổi trạng thái trong các bản phát hành sau; “false” không phải lời hứa tồn tại mãi mãi.

Trong một dự án Java hiện đại, cách đọc đúng là:

```text
Đang gọi một API đã bị đánh dấu @Deprecated?
                         |
                  forRemoval ?
                   /         \
               false         true
                 |             |
       [deprecation]         [removal]
       Chuyển đổi có kế hoạch  Chuyển đổi ưu tiên cao
                 \             /
                  \           /
              Xem tài liệu thay thế
              + kiểm tra tương thích JDK
```

Không có cơ chế nào của `@Deprecated` tự động chuyển lời gọi sang API mới. **Đội phát triển vẫn phải sửa mã** và kiểm thử hành vi thay thế.

## 2. Annotation `@Deprecated`: `since` và `forRemoval`

Annotation `java.lang.Deprecated` tồn tại từ lâu nhưng có hai thuộc tính `since` và `forRemoval` từ **Java 9**. Cú pháp hiện hành:

```java
@Deprecated(since = "17", forRemoval = false)
public static String oldName() {
    return "ordinary";
}

@Deprecated(since = "17", forRemoval = true)
public static String removedSoon() {
    return "terminal";
}
```

Đây là **hai phương thức minh họa**, chưa phải class hoàn chỉnh. Ý nghĩa từng thuộc tính:

- `since = "17"`: chuỗi mô tả **phiên bản bắt đầu bị deprecated**. Đây là **metadata cung cấp thông tin**; `javac` không tự thiết lập thời điểm xóa API dựa trên chuỗi này.
- `forRemoval = false`: giá trị **mặc định**. API vẫn bị deprecated, nhưng không có tín hiệu đang được chuẩn bị loại bỏ.
- `forRemoval = true`: báo hiệu **ý định loại bỏ**. Không định nghĩa ngày, bản phát hành hoặc thời hạn bắt buộc; cần đọc Javadoc và ghi chú phát hành của nhà cung cấp.
- Nếu viết chỉ `@Deprecated`, tương đương về trạng thái removal với `forRemoval=false`; giá trị `since` mặc định là chuỗi rỗng `""`.

Hai thuộc tính này **không tự thay đổi ngữ nghĩa thực thi** của phương thức. Nếu phương thức vẫn tồn tại, chương trình vẫn có thể gọi được nó tại runtime; rủi ro xuất hiện khi sau này API thực sự bị xóa hoặc thay đổi.

### Annotation khác Javadoc tag

Hai ký hiệu thường cùng xuất hiện nhưng **không cùng mục đích**:

| Cú pháp | Công dụng |
|---|---|
| `@Deprecated(since="17", forRemoval=true)` | Metadata mà compiler, IDE và công cụ phân tích nhận diện; tạo cảnh báo khi dùng |
| `@deprecated` (chữ **d thường**) trong `/** ... */` | Phần **tài liệu**: vì sao API không còn được khuyến nghị, dùng gì thay thế và có khác biệt hành vi nào |

Ví dụ đầy đủ trong một class:

```java
/**
 * @deprecated Từ bản 17, dùng {@link #current()} thay thế.
 *             Phương thức này có kế hoạch bị loại bỏ.
 */
@Deprecated(since = "17", forRemoval = true)
public static String removedSoon() {
    return "terminal";
}

public static String current() {
    return "modern";
}
```

Đây là **mảnh mã thuộc class**. Annotation tạo metadata cho `javac`, còn tag Javadoc giúp người đọc hiểu **đường di chuyển**. Đừng chỉ ghi `@deprecated` rồi quên annotation: khi bật `-Xlint:dep-ann`, `javac` có thể cảnh báo mục tài liệu được đánh deprecated mà thiếu `@Deprecated`. Tương tự, đặt annotation mà không giải thích phương án thay thế khiến người dùng API khó sửa mã dù đã thấy warning.

## 3. Ví dụ hai file Java 17+ chạy độc lập: sinh đúng hai nhóm cảnh báo

Để không phụ thuộc bất kỳ API JDK cũ đã bị xóa trong các bản mới, ví dụ dùng **API giả lập do chính chúng ta định nghĩa**. Cả hai phương thức deprecated vẫn hoạt động và trả kết quả rõ ràng.

Tạo hai file **trong cùng một thư mục**.

**Tệp `LegacyApi.java`:**

```java
public final class LegacyApi {

    private LegacyApi() {}

    /**
     * @deprecated Từ phiên bản 17, dùng {@link #modern()}.
     */
    @Deprecated(since = "17")
    public static String oldName() {
        return "ordinary";
    }

    /**
     * @deprecated Từ phiên bản 17, dùng {@link #modern()}.
     *             API này được đánh dấu để loại bỏ trong tương lai.
     */
    @Deprecated(since = "17", forRemoval = true)
    public static String removedSoon() {
        return "terminal";
    }

    public static String modern() {
        return "modern";
    }
}
```

**Tệp `DeprecationWarningsDemo.java`:**

```java
public final class DeprecationWarningsDemo {

    public static void main(String[] args) {
        System.out.println(LegacyApi.oldName());
        System.out.println(LegacyApi.removedSoon());
        System.out.println(LegacyApi.modern());
    }
}
```

### Chạy lần 1: javac ở chế độ mặc định

```bash
javac --release 17 -encoding UTF-8 LegacyApi.java DeprecationWarningsDemo.java
java DeprecationWarningsDemo
```

**Hành vi kiểm chứng trên JDK 24**: `javac` cho **1 cảnh báo `[removal]`** tại lời gọi `LegacyApi.removedSoon()`; đồng thời có thể in thông báo dạng `Note: ... uses or overrides a deprecated API.` và gợi ý `-Xlint:deprecation` cho lời gọi `oldName()`. Các chi tiết như đường dẫn, số dòng hay xuống dòng trong thông báo có thể khác giữa JDK, hệ điều hành và build tool.

Chương trình **vẫn chạy**. **Stdout của lệnh `java` chính xác**:

```text
ordinary
terminal
modern
```

Ba dòng này chứng minh: mặc dù có cảnh báo tại **compile time**, hai phương thức vẫn thực thi vì chúng còn tồn tại trong phiên bản `LegacyApi` đang sử dụng. Tuy nhiên, đó **không** phải lý do để giữ chúng lâu dài trong mã ứng dụng.

### Chạy lần 2: yêu cầu liệt kê cả hai nhóm

```bash
javac --release 17 -encoding UTF-8 \
  -Xlint:deprecation -Xlint:removal \
  LegacyApi.java DeprecationWarningsDemo.java
```

Trên Windows PowerShell, dùng một dòng:

```powershell
javac --release 17 -encoding UTF-8 -Xlint:deprecation -Xlint:removal LegacyApi.java DeprecationWarningsDemo.java
```

Với JDK 24 và đúng hai file trên, phần **nhãn cảnh báo quan trọng** là:

```text
warning: [deprecation] oldName() in LegacyApi has been deprecated
warning: [removal] removedSoon() in LegacyApi has been deprecated and marked for removal
2 warnings
```

Đây là **trích xuất phần nhãn và nội dung**; `javac` thực tế có thể thêm tên file, vị trí dòng, dấu ^ và khoảng trắng. Không coi ba dòng đã rút gọn là toàn bộ stderr byte-for-byte.

### Chạy lần 3: xem đúng loại bạn đang điều tra

```bash
javac --release 17 -encoding UTF-8 -Xlint:deprecation LegacyApi.java DeprecationWarningsDemo.java
javac --release 17 -encoding UTF-8 -Xlint:removal LegacyApi.java DeprecationWarningsDemo.java
```

- `-Xlint:deprecation` yêu cầu hiển thị chi tiết của **ordinary deprecation**. Vì removal được bật mặc định, câu lệnh thứ nhất vẫn có thể thấy **cả hai** warning; đó là điều bình thường.
- `-Xlint:removal` yêu cầu nhóm **removal**. Nó **không** có nghĩa tự động bật deprecation thông thường.
- Muốn chủ động vô hiệu hóa một nhóm trên toàn lượt biên dịch, dùng `-Xlint:-deprecation` hoặc `-Xlint:-removal` (chỉ khi bạn biết vì sao đang làm). Dấu `-` nằm **trước tên nhóm sau dấu hai chấm**.

**Kết luận thực tế:** Khi rà soát API, dùng cả `-Xlint:deprecation` và `-Xlint:removal` để không bỏ sót. Khi kiểm tra tác động nâng JDK, tập trung trước vào cảnh báo `[removal]`.

## 4. Vì sao removal thường hiển thị ngay cả khi chưa bật -Xlint?

Đây là một khác biệt quan trọng khi đọc log build:

```text
javac (cấu hình thông thường)
  │
  ├─ Dùng API @Deprecated(forRemoval=false)
  │    └─ có thể nhận Note tóm tắt
  │         "Recompile with -Xlint:deprecation for details."
  │
  └─ Dùng API @Deprecated(forRemoval=true)
       └─ có thể nhận warning chi tiết [removal]
          ngay với cấu hình mặc định
```

Theo tài liệu `javac` hiện hành, **nhóm removal là một trong các lint được bật mặc định**. Trong khi đó, ordinary deprecation nhiều trường hợp chỉ tạo thông báo tóm tắt nếu bạn chưa yêu cầu thông tin chi tiết.

Điều này giúp việc chuẩn bị loại bỏ API không bị chìm trong lượng cảnh báo đã deprecated lâu năm nhưng chưa lên kế hoạch xóa.

**Không đo độ nghiêm trọng bằng độ dài văn bản log.** Hai loại đều nên được xử lý. Removal cao ưu tiên hơn về tương thích phiên bản, nhưng ordinary deprecation có thể xuất phát từ lỗi logic hoặc an toàn mà ứng dụng cần khắc phục ngay.

### Phân biệt warning và error

Ví dụ trong mục 3 biên dịch thành công dù có cảnh báo. Nhưng nếu nhóm của bạn bật:

```bash
javac --release 17 -encoding UTF-8 -Xlint:deprecation -Xlint:removal -Werror LegacyApi.java DeprecationWarningsDemo.java
```

thì `-Werror` sẽ yêu cầu **coi cảnh báo là lỗi**, dẫn đến **biên dịch thất bại**. Đây là **chính sách build**; bản thân việc có `@Deprecated(forRemoval=true)` không làm compiler tự động cấm sử dụng API.

Trong Gradle/Maven, cấu hình compiler plugin hoặc lint khác có thể áp dụng `-Werror` hoặc thiết lập tương đương. Vì vậy hãy đối chiếu command line compiler **thật sự được build tool sử dụng** trước khi kết luận cảnh báo đã trở thành lỗi vì API bị xóa.

## 5. Cách tắt cảnh báo có mục đích: @SuppressWarnings

Nếu **chưa thể chuyển đổi ngay**, có thể giới hạn phạm vi suppress đến đúng method hoặc khai báo cần thiết:

| Annotation tại chỗ sử dụng | Nó tắt gì? |
|---|---|
| `@SuppressWarnings("deprecation")` | Chỉ cảnh báo ordinary deprecation |
| `@SuppressWarnings("removal")` | Chỉ cảnh báo removal |
| `@SuppressWarnings({"deprecation", "removal"})` | Cả hai nhóm |
| `@SuppressWarnings("all")` | Không phải cách thay thế đáng tin cậy cho hai nhóm trên; không nên dựa vào để xử lý API deprecated |

**Điểm hay bị nhầm:** `@SuppressWarnings("deprecation")` **không** tắt cảnh báo `[removal]`. Ngược lại `@SuppressWarnings("removal")` **không** tắt ordinary deprecation.

**Ví dụ độc lập với class LegacyApi ở mục 3** (chỉ minh họa suppression, không có `main`):

```java
public final class SuppressionDemo {

    private SuppressionDemo() {}

    @SuppressWarnings("deprecation")
    public static String onlyOrdinarySuppressed() {
        return LegacyApi.oldName() + LegacyApi.removedSoon();
        // Chỉ còn cảnh báo [removal] ở removedSoon().
    }

    @SuppressWarnings("removal")
    public static String onlyRemovalSuppressed() {
        return LegacyApi.oldName() + LegacyApi.removedSoon();
        // Chỉ còn cảnh báo [deprecation] ở oldName()
        // nếu bật -Xlint:deprecation.
    }

    @SuppressWarnings({"deprecation", "removal"})
    public static String bothSuppressed() {
        return LegacyApi.oldName() + LegacyApi.removedSoon();
        // Không còn hai nhóm cảnh báo tại method này.
    }
}
```

Để biên dịch và kiểm chứng hai warning còn lại:

```bash
javac --release 17 -encoding UTF-8 -Xlint:deprecation -Xlint:removal LegacyApi.java SuppressionDemo.java
```

Ở JDK 24, kết quả tạo **hai cảnh báo**: một `[removal]` trong `onlyOrdinarySuppressed()` và một `[deprecation]` trong `onlyRemovalSuppressed()`. Method `bothSuppressed()` không tạo warning thuộc hai nhóm này. Những nhận định trên đã được kiểm chứng với `javac`.

**Cách dùng đúng trong dự án thực:**

1. Chỉ suppress khi có lý do cụ thể (tương thích plugin, thời gian di chuyển, hoặc dùng API bắt buộc chưa có thay thế thích hợp).
2. Đặt annotation trên **khai báo hẹp nhất** chứa lời gọi chưa thay được, thay vì cả module hoặc class rất lớn.
3. Thêm comment giải thích vì sao tạm thời dùng API và điều kiện gỡ suppression; ví dụ “sẽ xóa sau khi nâng thư viện X”.
4. Tạo bài kiểm thử/thẻ công việc để theo dõi thay thế trước thời điểm nâng JDK.
5. **Không mặc định suppress removal** chỉ để có build “xanh”. Cảnh báo có thể là tín hiệu duy nhất rằng API biến mất ở bản JDK mới hơn.

Nếu không muốn suppress từng phương thức, có thể tắt nhóm cảnh báo cho cả lượt `javac` bằng tùy chọn `-Xlint:-...`, nhưng đó là giải pháp phạm vi rộng, khó kiểm soát và không được khuyến nghị cho codebase cần nâng cấp lâu dài.

## 6. Deprecation không phải removal: ba trạng thái cần phân biệt

Một API có thể đi qua những giai đoạn phát triển khác nhau:

```text
(1) API còn được hỗ trợ bình thường
            |
            v
(2) API bị deprecated
    @Deprecated(forRemoval=false)
    -> người dùng được khuyên ngừng gọi
            |
            | nhà cung cấp CÓ THỂ quyết định
            | đánh dấu forRemoval trong tương lai
            v
(3) API deprecated for removal
    @Deprecated(forRemoval=true)
    -> dự định xóa trong một bản sau
            |
            | có thể có một đợt phát hành loại bỏ
            v
(4) API đã bị xóa thật
    -> không còn khai báo/symbol tương ứng
    -> biên dịch nguồn cũ có thể lỗi
    -> binary cũ có thể lỗi liên kết nếu thiếu symbol
```

**Không phải mọi API deprecated đều trải qua mọi bước.** Một số API có thể tiếp tục tồn tại rất lâu; một số được đánh dấu removal nhưng thời điểm xóa thay đổi. Không suy luận “`since=17` thì JDK 18 chắc chắn xóa” — `since` chỉ là thời điểm bắt đầu deprecated. Cũng không suy luận “`forRemoval=true` nên hôm nay đã không chạy được”.

Khi API **thật sự đã bị xóa**, thông báo chuyển từ dạng warning sang lỗi như `cannot find symbol` khi biên dịch code dùng phương thức, hoặc lỗi liên kết ở runtime (ví dụ `NoSuchMethodError` đối với một phương thức đã bị xóa) khi chạy binary cũ với tập class không tương thích. **Suppress warning không thể khôi phục API đã mất.**

### Tại sao nên hiểu mức ưu tiên này?

- Một lời gọi deprecated thông thường có thể ảnh hưởng tính rõ ràng, thiết kế, bảo trì và đôi khi an toàn, nên vẫn cần xem lý do.
- Lời gọi `forRemoval=true` thường có **rủi ro tương thích trực tiếp** khi nâng phiên bản nền tảng/thư viện.
- Ngay cả khi ứng dụng chạy được ở JDK hiện tại, khả năng nâng phiên bản thành công còn phụ thuộc mã nguồn, dependency, binary và môi trường vận hành.

Quyết định chuyển đổi phải dựa vào **Javadoc của API cụ thể**, tài liệu migration và phiên bản runtime thực tế, không chỉ nhìn mã cảnh báo.

## 7. Tác giả thư viện nên đánh dấu deprecated như thế nào?

Nếu bạn duy trì một thư viện Java 17+ và muốn chuyển người dùng sang API mới, hãy phối hợp **annotation, Javadoc và kế hoạch phát hành**.

Ví dụ trong class quản lý cấu hình:

```java
import java.nio.charset.StandardCharsets;

public final class TextCodec {

    private TextCodec() {}

    /** Mã hóa văn bản sang UTF-8 theo cách được hỗ trợ hiện nay. */
    public static byte[] encodeUtf8(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    /**
     * @deprecated Từ bản 17, sử dụng {@link #encodeUtf8(String)}.
     *             Tên cũ không truyền đạt rõ charset được chọn.
     */
    @Deprecated(since = "17", forRemoval = false)
    public static byte[] encode(String text) {
        return encodeUtf8(text);
    }
}
```

Đây là **tệp `TextCodec.java` hoàn chỉnh, có thể biên dịch**. Nó minh họa chính sách chuyển đổi mà không yêu cầu người học sử dụng một API JDK lỗi thời. Phương thức `encode` là ví dụ giả định về phiên bản cũ của **thư viện tự xây dựng**, không phải tên API JDK thực tế.

Khi có kế hoạch loại bỏ thật, chủ thư viện có thể đổi annotation thành:

```java
@Deprecated(since = "17", forRemoval = true)
public static byte[] encode(String text) {
    return encodeUtf8(text);
}
```

Đây là **mảnh mã** minh họa thay đổi trạng thái, không phải yêu cầu tự động thay thế phương thức trong ví dụ đã biên dịch. Khi đổi `forRemoval`:

- Không được sửa `since` thành thời điểm bật `forRemoval` nếu mục đích của `since` là ghi lại **lần đầu API bị deprecated**.
- Cập nhật Javadoc và ghi chú phát hành để nêu ý định và hướng chuyển đổi.
- Bảo đảm API mới đáp ứng công dụng thực tế; tài liệu cần giải thích khác biệt đầu vào/đầu ra, exception, charset, thread safety... nếu có.
- Nếu thực sự xóa phương thức ở một bản sau, đó là thay đổi tương thích riêng và cần đánh giá theo chính sách versioning của thư viện.

**Không nên gắn `forRemoval=true` chỉ để đe dọa người dùng.** Đây là metadata có ý nghĩa cho compiler và công cụ phân tích; nên phản ánh kế hoạch bảo trì thực.

## 8. @deprecated trong Javadoc và danh sách Deprecated API

Khi sinh Javadoc cho thư viện, thông tin deprecated có thể được trình bày tại:

- Trang của class/method: thể hiện annotation và mô tả chuyển đổi từ thẻ `@deprecated`.
- **Deprecated API list**: trang tổng hợp các API deprecated trong bộ tài liệu (tùy cấu hình doclet).
- Mục riêng cho API **deprecated for removal** khi bộ tài liệu/doclet phân nhóm trạng thái này.

Ví dụ chuẩn của JDK hiện hành:
[Deprecated API List — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/deprecated-list.html).

Cách đọc:

1. Xác định đúng **tên phần tử và module/package**, vì các overload cùng tên có thể có trạng thái deprecated khác nhau.
2. Đọc `@Deprecated(forRemoval=...)` hoặc chú thích “deprecated, for removal” ở bản JDK bạn **định nâng tới**.
3. Đọc ***vì sao*** bị deprecated; không nhất thiết mọi phương thức cũ đều có API thay thế 1-1.
4. Xem API thay thế có khác biệt hành vi, dữ liệu, phạm vi truy cập hoặc điều kiện ngoại lệ hay không.
5. Kiểm tra có thông báo xóa trong release notes/migration guide hay chưa.

**Lưu ý:** Trang Deprecated API của JDK 27 **không** thể thay danh sách deprecated của một thư viện bên thứ ba. Thư viện của bạn cần xem Javadoc riêng, changelog và semantic-version policy của chính thư viện ấy.

## 9. Công cụ kiểm tra trên codebase hiện đại

### javac: bắt cảnh báo từ mã nguồn

Khi muốn rà soát code hiện có, cách trực tiếp nhất là biên dịch với:

```bash
javac -Xlint:deprecation -Xlint:removal MyApplication.java
```

Lệnh này chỉ là **mẫu cú pháp** nếu bạn có tệp `MyApplication.java` và dependency phù hợp. Đối với dự án nhiều class/module, dùng chính lệnh build của dự án và truyền hai tham số lint vào cấu hình compiler, thay vì chỉ biên dịch một source file rồi kết luận không còn warning.

Nếu chính sách dự án yêu cầu mọi warning phải được xử lý, có thể bật `-Werror` sau khi đã kiểm soát được lượng warning; khi đó compiler trả exit code thất bại nếu phát sinh cảnh báo.

### jdeprscan: tìm sử dụng API deprecated thuộc Java SE

JDK hiện đại có công cụ **`jdeprscan`** để phân tích **class file, thư mục class hoặc JAR** nhằm tìm những API **thuộc Java SE** đã deprecated. Ví dụ:

```bash
jdeprscan path/to/application.jar
jdeprscan --for-removal path/to/application.jar
```

Hai lệnh trên là mẫu cần thay `path/to/application.jar` bằng một **JAR đã tồn tại và có đủ dependency cần thiết**. Lệnh thứ hai chỉ quan tâm các API Java SE được đánh dấu for removal. Khi phân tích phụ thuộc phiên bản, công cụ còn có tùy chọn `--release` (những bản hỗ trợ phụ thuộc JDK cài trên máy).

**Giới hạn quan trọng:**

- `jdeprscan` **không báo mọi API deprecated trong thư viện bên thứ ba**. Ví dụ nó không tự biết các lời gọi vào `LegacyApi` của bài này, vì đó là class tự tạo.
- Nếu class liên quan không nằm trên classpath, công cụ có thể không phân tích đầy đủ; cần bổ sung `--class-path`.
- Kết quả tùy **bản JDK chạy jdeprscan** và tập API Java SE mà bản đó biết.
- `jdeprscan` là công cụ bổ sung; không thay kiểm thử biên dịch, kiểm thử runtime hoặc phân tích cảnh báo của compiler đối với các dependency không thuộc Java SE.

### IDE và CI/CD

IDE thường gạch hoặc tô API deprecated và hiển thị thông tin `forRemoval`. Tuy nhiên, khi CI dùng một JDK khác máy lập trình viên, danh sách API deprecated của JDK có thể khác. Nên:

1. Cố định hoặc ghi rõ bản JDK mục tiêu của build/CI.
2. Bật lint chi tiết cho cả hai loại.
3. Phân loại rủi ro: removal sớm ưu tiên xử lý, ordinary deprecation tiếp tục có kế hoạch.
4. Kiểm tra đường chuyển đổi bằng test; không chỉ sửa để mất cảnh báo.
5. Khi nâng JDK hoặc cập nhật dependency, chạy lại compiler warning scan và test ở môi trường thực tế.

## 10. Các tình huống dễ nhầm khi đọc warning

| Tình huống | Cách hiểu đúng và hướng xử lý |
|---|---|
| “Compile thấy `[removal]`, nghĩa là hôm nay không dùng API được nữa” | Sai. API thường vẫn tồn tại ở bản đang biên dịch; warning báo ý định loại bỏ trong tương lai. |
| “`forRemoval=false` là đảm bảo Java không bao giờ xóa” | Sai. Đó là trạng thái tại thời điểm đánh dấu; có thể thay đổi ở một bản sau. |
| “`since="17"` nghĩa là sẽ bị xóa ở Java 17” | Sai. `since` là phiên bản **bắt đầu deprecated**, không phải thời hạn xóa. |
| “`@SuppressWarnings("deprecation")` sẽ chặn mọi cảnh báo deprecated” | Sai. Nó không chặn `[removal]`; dùng khóa `"removal"` cho nhóm kia. |
| “Đã suppress warning thì chạy được với JDK mới” | Sai. Suppression không đem lại API đã xóa hoặc giải quyết thay đổi hành vi. |
| “Không thấy warning nào ở `javac` mặc định nên mã không dùng deprecated API” | Sai. Ordinary deprecation có thể chỉ được thông báo dưới dạng `Note`; hãy bật `-Xlint:deprecation`. |
| “Cảnh báo removal luôn nghiêm trọng hơn mọi cảnh báo ordinary deprecation về mặt bảo mật” | Không thể khẳng định. Removal báo rủi ro tương thích, còn ordinary deprecation cũng có thể cảnh báo API có vấn đề an toàn/thiết kế. |
| “Chỉ cần thêm `@deprecated` trong Javadoc là compiler luôn phát removal warning” | Sai. Cần annotation `@Deprecated(forRemoval=true)`; thẻ Javadoc chỉ cung cấp tài liệu. |
| “Bật `-Xlint:dep-ann` cũng giống `-Xlint:deprecation`” | Sai. `dep-ann` kiểm tra Javadoc tag thiếu annotation; `deprecation` cảnh báo **lời gọi** tới API ordinarily deprecated. |
| “`-Werror` là một đặc tính chỉ của removal” | Sai. `-Werror` biến **mọi cảnh báo được compiler phát ra** thành lỗi build. |
| “`jdeprscan` sẽ báo toàn bộ thư viện đang deprecated của Maven” | Sai. Nó tập trung vào API deprecated của Java SE; kiểm tra thư viện bên ngoài bằng compiler, IDE và tài liệu bên thứ ba. |
| “Xóa phương thức thì người dùng sẽ chỉ nhận warning `[removal]`” | Sai. Khi phương thức đã mất thật, mã nguồn có thể gặp lỗi symbol và binary cũ có thể gặp lỗi liên kết runtime. |

## 11. Chiến lược migration theo mức độ ưu tiên

Giả sử build phát hiện hàng chục deprecated warning, không nên chỉ tắt hết để sạch log. Một quy trình có thể áp dụng:

**Bước 1 — Kiểm kê.** Chạy build trên JDK mục tiêu với `-Xlint:deprecation -Xlint:removal`; ghi rõ file, method, loại warning, API thay thế và bản JDK/dependency đang chạy.

**Bước 2 — Ưu tiên removal.** Với `[removal]`, đọc tài liệu của nhà cung cấp để biết các bản đã có kế hoạch xóa. Nếu đang nâng JDK, kiểm tra API có còn trong bản đích hay không. Nếu đã mất, không thể chỉ suppress.

**Bước 3 — Phân tích ngữ nghĩa thay thế.** Thay lời gọi cũ bằng API được khuyến nghị; chú ý khác biệt exception, charset, đối tượng trả về, quyền truy cập, vấn đề tài nguyên hoặc khả năng đồng thời. Không coi đổi tên method là đủ.

**Bước 4 — Kiểm thử.** Chạy unit test, integration test và test liên quan đến nhiều bản JDK nếu sản phẩm hỗ trợ. Với thư viện, kiểm tra tính tương thích nguồn và binary theo chính sách phát hành.

**Bước 5 — Xử lý ordinary deprecation.** Sửa dần các API còn deprecated thông thường và tài liệu hóa trường hợp chưa thể thay thế.

**Bước 6 — Suppress tối thiểu nếu bắt buộc.** Chỉ suppress nơi có lý do được xem xét, không suppress chung ở toàn dự án. Có kế hoạch bỏ suppression trước đợt nâng cấp lớn.

**Bước 7 — Ngăn phát sinh mới.** Dùng lint trong CI để phát hiện thêm lời gọi deprecated; tùy quy mô có thể áp dụng `-Werror` ở các module đã được làm sạch.

**Vì sao không nên tìm bản “xóa ngay ở JDK tiếp theo” chỉ từ forRemoval?** Vì `@Deprecated` không mang metadata phiên bản dự kiến xóa. Đó là thông tin phát hành/chính sách ngoài annotation. Việc chưa có ngày cụ thể không làm mất giá trị ưu tiên của removal warning.

## 12. Tự kiểm tra hiểu biết

1. **Hai phương thức cùng mang `@Deprecated` thì compiler luôn báo giống nhau?** Không; `forRemoval=false` tạo ordinary deprecation, `forRemoval=true` tạo removal warning.
2. **Giá trị mặc định của `forRemoval` là gì?** `false`.
3. **Nếu có `@Deprecated(since="17", forRemoval=true)`, API chắc chắn bị xóa trong Java 18?** Không. `since` mô tả khi bắt đầu deprecated; `forRemoval` không đặt deadline.
4. **Muốn hiện đầy đủ cả hai loại cảnh báo phải dùng gì?** `javac -Xlint:deprecation -Xlint:removal`.
5. **Lúc không có `-Xlint:deprecation` vẫn thấy `[removal]` có lạ không?** Không. Nhóm removal thường được bật mặc định trong `javac`.
6. **Muốn suppress chỉ removal tại một method?** Dùng `@SuppressWarnings("removal")` ngay trên method đó, kèm lý do khi cần.
7. **`@SuppressWarnings("deprecation")` có tắt removal không?** Không.
8. **`@deprecated` và `@Deprecated` khác nhau thế nào?** Tag chữ thường là tài liệu Javadoc; annotation chữ hoa là metadata cho compiler và công cụ.
9. **Nếu đã bị xóa thực sự, suppression có giúp compile thành công?** Không. Không còn symbol thì phải đổi mã hoặc thay phiên bản dependency phù hợp.
10. **Công cụ `jdeprscan` có dò mọi deprecated API tự định nghĩa của dự án không?** Không; trọng tâm của nó là các API deprecated của Java SE.
11. **Dùng `-Werror` thì điều gì xảy ra?** Các warning được `javac` phát ra khiến build thất bại, không chỉ riêng removal.
12. **Tại sao cần đọc tài liệu API thay thế?** Vì phương thức mới có thể khác ngữ nghĩa và yêu cầu kiểm thử, không chỉ khác tên.

## Tài liệu chính thức còn áp dụng

- [Java SE 27: `java.lang.Deprecated` API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Deprecated.html)
- [The javac Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html)
- [Notifications and Warnings — Java Core Libraries (JDK 25)](https://docs.oracle.com/en/java/javase/25/core/notifications-and-warnings.html)
- [Deprecated API List — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/deprecated-list.html)
- [How to Deprecate APIs — Oracle Java Core Libraries](https://docs.oracle.com/en/java/javase/21/core/how-deprecate-apis.html)
- [The jdeprscan Command — JDK 21 (khả dụng trên JDK hiện hành)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html)
- [JEP 277 — Enhanced Deprecation](https://openjdk.org/jeps/277)
