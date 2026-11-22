# @Deprecated trong Java: since, forRemoval và thẻ Javadoc @deprecated

Khi một API Java không còn được khuyến khích sử dụng, tác giả thư viện cần báo cho người gọi biết **API nào đã lỗi thời, bị đánh dấu từ phiên bản nào, có dự định bị xóa hay không, và nên chuyển sang API nào**. Java hỗ trợ việc đó bằng annotation `@Deprecated` và thẻ Javadoc `@deprecated`.

Hai cơ chế bổ sung cho nhau:

- `@Deprecated` là **annotation Java** gắn vào khai báo, cung cấp metadata để trình biên dịch và công cụ nhận biết; từ Java 9 có hai thành phần `since` và `forRemoval`.
- `@deprecated` là **thẻ nằm trong khối Javadoc `/** ... */`**, dùng giải thích lý do và hướng di chuyển. Đây không phải annotation Java.

Phần lớn API deprecated **vẫn tồn tại và có thể gọi được** ở phiên bản hiện tại. Deprecation là tín hiệu cần cân nhắc di chuyển, không phải một lệnh tự động vô hiệu hóa method.

## 1. @Deprecated thông báo điều gì?

Annotation chuẩn `java.lang.Deprecated` đã có từ Java 5; kể từ Java 9, nó hỗ trợ:

```java
@Deprecated(since = "2.1", forRemoval = true)
public void oldOperation() {
    // API đời cũ
}
```

Đây là **đoạn minh họa method**, cần đặt trong class phù hợp nếu muốn biên dịch. Ý nghĩa:

- `since = "2.1"`: tác giả API cho biết phần tử **bắt đầu được đánh dấu deprecated ở phiên bản 2.1**. Với thư viện tự xây, đây có thể là phiên bản thư viện, không nhất thiết là phiên bản JDK.
- `forRemoval = true`: tác giả **có ý định xóa API trong một phiên bản tương lai**. Người sử dụng cần ưu tiên chuyển đổi.
- Nếu không ghi `forRemoval`, giá trị mặc định là `false`. Nếu không ghi `since`, giá trị mặc định là chuỗi rỗng `""`.

Thông tin `since` giúp truy vết lịch sử; `forRemoval` giúp đánh giá mức độ cấp bách của việc di chuyển. Không thuộc tính nào tự xóa method hoặc tự đặt thời điểm xóa.

### Bảng diễn giải từng trường hợp

| Khai báo | `since()` | `forRemoval()` | Diễn giải |
| --- | --- | --- | --- |
| `@Deprecated` | `""` | `false` | Đã deprecated nhưng chưa nêu phiên bản bắt đầu; không khai báo ý định xóa tại thời điểm đánh dấu |
| `@Deprecated(since = "2.0")` | `"2.0"` | `false` | Deprecated kể từ 2.0; nên ngừng dùng |
| `@Deprecated(forRemoval = true)` | `""` | `true` | Có ý định xóa nhưng không ghi phiên bản đánh dấu |
| `@Deprecated(since = "3.0", forRemoval = true)` | `"3.0"` | `true` | Deprecated từ 3.0 và dự kiến xóa sau này |

`false` **không cam kết API tồn tại vĩnh viễn**. Nó chỉ cho biết ở thời điểm khai báo không có ý định xóa cụ thể. Chính sách của thư viện có thể thay đổi ở những bản sau, đồng thời người dùng vẫn nên tìm cách thay thế.

## 2. since là phiên bản bắt đầu deprecated, không phải phiên bản tạo API

Hai mốc thời gian rất dễ bị nhầm:

- **Introduced**: API xuất hiện lần đầu khi nào?
- **Deprecated**: từ phiên bản nào tác giả bắt đầu khuyên không nên dùng?

Ví dụ một method được phát hành ở phiên bản 1.0, nhưng chỉ deprecated ở phiên bản 2.4:

```java
/**
 * Tạo mã định danh theo định dạng cũ.
 *
 * @since 1.0
 * @deprecated Từ phiên bản 2.4, dùng {@link #newId()}.
 */
@Deprecated(since = "2.4")
public String oldId() {
    return "OLD-01";
}

public String newId() {
    return "NEW-01";
}
```

Đây là đoạn **minh họa method** thuộc cùng một class; hai method dùng chung với nhau. Trong ví dụ:

- `@since 1.0` là **thẻ Javadoc**: API được giới thiệu từ 1.0.
- `@Deprecated(since = "2.4")` là **metadata annotation**: API bắt đầu deprecated ở 2.4.
- `@deprecated ...` giải thích cách chuyển sang `newId()`.

Cả `@since` và `@deprecated` đều được viết bên trong comment Javadoc. Chúng khác hẳn `since()` của annotation `@Deprecated`.

`since` là dữ liệu mô tả phiên bản (kiểu `String`), Java không tự so sánh nó với phiên bản JDK đang chạy và cũng không tự thực thi một thời hạn di chuyển. Khi duy trì thư viện, hãy thống nhất quy ước phiên bản và ghi đúng phiên bản phát hành lần đầu có trạng thái deprecated.

### Liên quan đến phiên bản Java

`@Deprecated` đã tồn tại từ Java 5, nhưng **hai thuộc tính `since` và `forRemoval` chỉ được bổ sung từ Java 9**. Nếu phải biên dịch bằng JDK 8, cú pháp `@Deprecated(since = "9")` không hợp lệ vì định nghĩa annotation trên Java 8 chưa có thành phần đó. Với ví dụ học tập bên dưới, sử dụng JDK 17 trở lên.

## 3. forRemoval: phân biệt deprecated thông thường với deprecated để xóa

`forRemoval` là `boolean`. Nó quyết định cách trình biên dịch phân loại cảnh báo khi code khác sử dụng phần tử deprecated:

| Trạng thái | Thuật ngữ | Cảnh báo từ `javac` |
| --- | --- | --- |
| `forRemoval = false` | Ordinary deprecation | `deprecation` |
| `forRemoval = true` | Terminal deprecation / deprecated for removal | `removal` |

Với Java 17+, khi code gọi API có `forRemoval = true`, `javac` thường hiển thị cảnh báo `[removal]` ngay ở chế độ mặc định vì nhóm `-Xlint:removal` được bật mặc định. Với deprecation thông thường, lệnh biên dịch cơ bản có thể chỉ hiện ghi chú tổng quát; dùng `-Xlint:deprecation` để thấy chi tiết tại call site.

Các lệnh có ích:

```bash
javac -Xlint:deprecation -Xlint:removal Consumer.java
javac -Xlint:-deprecation Consumer.java
javac -Xlint:-removal Consumer.java
```

Những lệnh trên là **cú pháp để minh họa tùy chọn compiler**; cần có tệp `Consumer.java` chứa chương trình tương ứng mới chạy được. Có thể dùng riêng hai cờ bật lint trong một lần biên dịch. Không nên tắt cảnh báo trên toàn dự án chỉ vì chưa kịp di chuyển.

### true không có nghĩa “xóa ngay”

Xét `@Deprecated(since = "3.0", forRemoval = true)`. Java không lên lịch xóa API ở phiên bản 3.1, 4.0 hay một ngày cố định nào. Nó chỉ thông báo **ý định** của người duy trì. Ngay tại phiên bản đang chạy, method vẫn có thể tồn tại và hoạt động bình thường.

Khi API thực sự bị xóa trong một phiên bản thư viện mới:

- Source gọi API cũ có thể biên dịch lỗi vì không còn class hoặc method tương ứng.
- Bytecode đã biên dịch trước đó có thể thất bại khi liên kết/chạy với phiên bản thư viện mới, ví dụ `NoSuchMethodError`, tùy thay đổi cụ thể.
- Annotation và Javadoc không tự chuyển các lời gọi cũ sang API mới.

Vì thế, cảnh báo removal nên được xử lý sớm hơn cảnh báo deprecation thông thường, đặc biệt trong mã của thư viện nền tảng được nhiều module dùng lại.

## 4. Quan hệ giữa annotation @Deprecated và thẻ Javadoc @deprecated

Hai dòng gần giống nhau về chữ viết nhưng nằm ở **hai lớp xử lý khác nhau**:

```java
/**
 * Xử lý bằng thuật toán cũ.
 *
 * @deprecated Dùng {@link #modern()} vì thuật toán mới rõ ràng hơn.
 */
@Deprecated(since = "2.0", forRemoval = false)
public String legacy() {
    return "legacy";
}

public String modern() {
    return "modern";
}
```

Đây là **hai method minh họa trong cùng class**, không phải tệp Java độc lập.

**Annotation `@Deprecated`:**

- Có chữ `D` viết hoa; đứng ngoài Javadoc, trước khai báo.
- Được ghi thành annotation metadata của Java; `@Deprecated` có retention `RUNTIME`.
- Cho phép `javac`, IDE, reflection và công cụ phân tích biết trạng thái deprecated, gồm `since` và `forRemoval`.
- Không chứa phần giải thích nghiệp vụ hay hướng thay thế cụ thể.

**Thẻ Javadoc `@deprecated`:**

- Có chữ `d` viết thường; chỉ là thẻ đặc biệt trong khối `/** ... */`.
- Cung cấp **lý do**, tác động, API thay thế và lưu ý di chuyển cho người đọc tài liệu.
- Được `javadoc` dùng khi sinh tài liệu HTML, thường nổi bật trong phần mô tả phần tử deprecated.
- Không phải annotation type; không có hai thành phần `since()` và `forRemoval()` và không truy xuất bằng `getAnnotation()`.

**Quy ước nên tuân thủ: khai báo API deprecated bằng cả hai.** Nếu có `@Deprecated` nhưng không viết Javadoc `@deprecated`, công cụ vẫn phát hiện deprecated nhưng người dùng có thể không biết phải thay bằng gì. Nếu có `@deprecated` trong Javadoc mà thiếu annotation, `javac` hiện đại có thể cảnh báo loại `[dep-ann]` vì tài liệu và metadata không nhất quán.

Không nên nói rằng thẻ Javadoc một mình “hoàn toàn vô hình với compiler”: một số công cụ, gồm `javac`, cũng kiểm tra nội dung doc comment để phát cảnh báo tính nhất quán. Tuy nhiên, **cơ chế chuẩn để đánh dấu deprecation của Java và cung cấp giá trị `since/forRemoval` vẫn là annotation**.

### Ví dụ đối chiếu bốn trường hợp

| Khai báo | Compiler/công cụ | Tài liệu cho người đọc |
| --- | --- | --- |
| Chỉ `// deprecated` | Chỉ là comment thông thường, không đánh dấu deprecated | Không tạo thẻ deprecation |
| Chỉ thẻ Javadoc `@deprecated` | Có thể xuất hiện cảnh báo `dep-ann` vì thiếu annotation | Có thông báo/lý do trong tài liệu |
| Chỉ annotation `@Deprecated` | Có metadata deprecated và cảnh báo sử dụng tương ứng | Thiếu giải thích thay thế ở thẻ tài liệu |
| Có cả hai | Metadata và cảnh báo được xác định bằng annotation | Có lý do, hướng dẫn, API mới trong Javadoc |

### Viết thông báo @deprecated tốt

Thẻ Javadoc nên trả lời:

1. **Vì sao deprecated?** Không an toàn, không chính xác, hành vi mơ hồ, đã có API mới, hoặc thay đổi kiến trúc?
2. **Thay bằng gì?** Trỏ tới method/class mới bằng `{@link ...}` nếu áp dụng được.
3. **Có khác biệt hành vi không?** Đổi đơn vị, cách xử lý `null`, định dạng dữ liệu, ngoại lệ hoặc trạng thái.
4. **Khi nào cần di chuyển?** Có thể ghi rõ chính sách của thư viện và cảnh báo removal, nhưng không hứa phiên bản xóa nếu chưa có kế hoạch công bố.

Ví dụ tốt hơn mô tả mơ hồ “Do not use”:

```java
/**
 * Trả về giá trị thời gian theo giây, làm tròn xuống.
 *
 * @deprecated Từ 2.5, dùng {@link #durationMillis()} để tránh
 *             mất độ chính xác khi giá trị nhỏ hơn một giây.
 *             Phép đổi đơn vị: giây = mili giây / 1000.
 */
@Deprecated(since = "2.5")
public long durationSeconds() {
    return durationMillis() / 1000;
}

public long durationMillis() {
    return 1500;
}
```

Trong đoạn minh họa trên, API cũ và API mới có đơn vị khác nhau. Người di chuyển cần xem lại code gọi; **không nên thay tên method một cách máy móc mà giữ nguyên mọi phép tính**.

## 5. Ví dụ độc lập Java 17+: đọc since và forRemoval bằng reflection

Tạo tệp **`DeprecationDemo.java`** chứa toàn bộ mã sau. Ví dụ cố tình **không gọi trực tiếp method deprecated**; nó đọc metadata bằng reflection và gọi API thay thế. Nhờ vậy, stdout dễ kiểm chứng mà không nhầm với cảnh báo khi biên dịch.

```java
import java.lang.reflect.Method;

/**
 * Minh họa trạng thái deprecated của API.
 */
public class DeprecationDemo {

    static class LegacyApi {

        /**
         * Trả về định dạng tên cũ.
         *
         * @since 1.0
         * @deprecated Từ phiên bản 2.0, dùng {@link #modernName()}.
         */
        @Deprecated(since = "2.0")
        public String oldName() {
            return "old";
        }

        /**
         * Trả về định dạng tên thử nghiệm không còn phù hợp.
         *
         * @deprecated Từ 3.0, dùng {@link #modernName()}.
         *             Method này được đánh dấu để xóa ở bản tương lai.
         */
        @Deprecated(since = "3.0", forRemoval = true)
        public String fragileName() {
            return "fragile";
        }

        /**
         * API thay thế nên sử dụng.
         *
         * @return tên theo định dạng mới
         */
        public String modernName() {
            return "modern";
        }
    }

    private static void inspect(String methodName)
            throws NoSuchMethodException {
        Method method = LegacyApi.class.getDeclaredMethod(methodName);
        Deprecated deprecated = method.getAnnotation(Deprecated.class);

        if (deprecated != null) {
            System.out.println(methodName
                    + ": since=" + deprecated.since()
                    + ", forRemoval=" + deprecated.forRemoval());
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        inspect("oldName");
        inspect("fragileName");
        System.out.println(new LegacyApi().modernName());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 DeprecationDemo.java
java DeprecationDemo
```

Stdout **chính xác** của lệnh `java DeprecationDemo`:

```text
oldName: since=2.0, forRemoval=false
fragileName: since=3.0, forRemoval=true
modern
```

Giải thích từng dòng:

1. `oldName` ghi `@Deprecated(since = "2.0")`; do không chỉ định `forRemoval`, reflection đọc được `false`.
2. `fragileName` ghi cả `since` và `forRemoval = true`, vì vậy reflection đọc đúng hai giá trị đó.
3. `modernName()` là API đang dùng bình thường; kết quả `modern` đến từ thân method.

Annotation `@Deprecated` có retention runtime, nên có thể truy vấn qua reflection. **Reflection không lấy được nội dung thẻ Javadoc `@deprecated`** bằng `method.getAnnotation()`. Javadoc tồn tại ở nguồn để công cụ tài liệu xử lý.

Tạo trang HTML để xem thẻ `@deprecated` và các liên kết thay thế:

```bash
javadoc -private -encoding UTF-8 -docencoding UTF-8 -d docs DeprecationDemo.java
```

Tham số `-private` cho phép tài liệu bao gồm cả lớp lồng `LegacyApi` không khai báo `public` trong ví dụ. Lệnh sinh tài liệu có thể in ghi chú/cảnh báo tùy JDK; những thông báo đó **không phải stdout của `DeprecationDemo`**.

### Khi gọi API cũ thì sao?

Đoạn sau chỉ minh họa **một nơi sử dụng trong code khác**, không phải thay thế trực tiếp nội dung tệp ví dụ độc lập ở trên:

```java
// Giả sử api là đối tượng LegacyApi từ ví dụ.
api.oldName();      // ordinary deprecation
api.fragileName();  // removal warning
```

Nếu biên dịch call site đó với `-Xlint:deprecation -Xlint:removal`, compiler có thể báo các warning ở những lời gọi tương ứng. Warning là **chẩn đoán lúc biên dịch**, không phải ngoại lệ runtime và không làm method tự động ngừng chạy.

## 6. Cảnh báo và @SuppressWarnings khi di chuyển API

Đối với code tiêu thụ thư viện, hai loại warning được xử lý độc lập:

```java
@SuppressWarnings("deprecation")
public void stillUsingOrdinaryDeprecation() {
    // Những lời gọi API deprecated thông thường bên trong
    // có thể được miễn cảnh báo "deprecation".
}

@SuppressWarnings("removal")
public void temporarilyUsingRemovalApi() {
    // Chỉ miễn cảnh báo "removal" trong phạm vi method.
}
```

Hai method ở trên là **minh họa cú pháp**, chưa chứa lời gọi API thật. `@SuppressWarnings("deprecation")` không tự động che cảnh báo `removal`, và ngược lại. Có thể dùng `@SuppressWarnings({"deprecation", "removal"})` nếu thực sự cần cả hai, nhưng phải có lý do và kế hoạch loại bỏ mã cũ.

Các cách xử lý hợp lý theo mức độ ưu tiên:

- Tìm API thay thế và xem sự khác biệt về hợp đồng hoạt động.
- Viết test bao phủ các trường hợp quan trọng trước/sau khi di chuyển.
- Với `forRemoval = true`, ưu tiên lập kế hoạch di chuyển vì có khả năng không còn API ở bản sau.
- Chỉ tạm suppress warning ở phạm vi nhỏ khi cần giữ tương thích; không dùng suppress như bằng chứng rằng API đã an toàn.

Trong ứng dụng lớn, có thể dùng `jdeprscan` để kiểm tra bytecode dùng **API deprecated của JDK**; nó không phải công cụ tổng quát phát hiện mọi annotation deprecated của mọi thư viện bên thứ ba. Muốn kiểm tra thư viện riêng, kết hợp lint, kiểm tra dependency và công cụ phân tích tương ứng.

## 7. Những giới hạn cần nhớ khi thiết kế và phát hành thư viện

**Deprecation không phải xóa API.** Thư viện nên giữ API cũ trong một giai đoạn chuyển tiếp phù hợp với chính sách tương thích. Chỉ đánh dấu `forRemoval = true` khi có ý định xóa; một dự định như vậy nên được truyền thông trong tài liệu phát hành.

**Giữ mô tả chính xác.** Nếu phiên bản đầu đánh dấu deprecated là 2.0, không đặt `since = "1.0"` chỉ vì API xuất hiện từ 1.0. Giá trị này nói về **lần đầu deprecated**, không phải lần đầu tồn tại.

**Không gắn sai ý nghĩa của forRemoval.** Đánh dấu `true` không đặt hạn sử dụng do JVM thực thi. Nó cũng không tự tạo phương án thay thế; thẻ `@deprecated` vẫn cần nói rõ cách đổi.

**Dùng đúng Javadoc.** Viết `// @deprecated` hoặc `/* @deprecated ... */` theo dạng comment thường không tạo thẻ Javadoc chuẩn. Thẻ `@deprecated` cần nằm trong comment `/** ... */` và có phần nội dung ngay sau thẻ.

**Dùng annotation và thẻ tài liệu cùng nhau.** Annotation cho compiler/công cụ; thẻ tài liệu cho người dùng API. Thiếu một trong hai sẽ làm thông tin không đầy đủ, và thiếu annotation khi đã có tag có thể gây cảnh báo `dep-ann`.

**Hiểu phiên bản thư viện.** Khi áp dụng vào module Java tự xây, `since = "4.0"` là phiên bản của chính thư viện đó nếu nhóm phát triển dùng quy ước ấy; không bắt buộc là Java 4.0 (và Java 4.0 cũng không phải baseline ngôn ngữ hiện tại).

## 8. Lỗi phổ biến và cách nhận biết

| Nhầm lẫn | Điều đúng cần nhớ |
| --- | --- |
| “`@Deprecated` làm API không gọi được nữa” | API vẫn có thể chạy khi phần tử còn tồn tại; compiler thông báo rủi ro |
| “`since` là phiên bản method được tạo” | Là phiên bản bắt đầu bị deprecated |
| “`forRemoval = true` xóa method ở lần build sau” | Chỉ báo ý định xóa ở một phiên bản tương lai |
| “`forRemoval = false` bảo đảm không bao giờ bị xóa” | Không có bảo đảm tồn tại vĩnh viễn |
| “`@deprecated` trong Javadoc chính là annotation” | Là thẻ tài liệu, chữ `d` viết thường |
| “Viết mỗi annotation là đủ hướng dẫn người dùng di chuyển” | Cần Javadoc với lý do, liên kết và khác biệt hành vi |
| “`@SuppressWarnings("deprecation")` che cả removal warning” | Cần `"removal"` cho nhóm warning riêng |
| “Reflection sẽ lấy được lời mô tả `@deprecated`” | Reflection đọc annotation runtime, không đọc doc comment |
| “Java 8 hỗ trợ `since`/`forRemoval` của annotation” | Hai thành phần này xuất hiện từ Java 9 |

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Trong `@Deprecated(since = "5.0")`, `5.0` là phiên bản API được tạo hay lần đầu deprecated?

**Đáp án:** Là phiên bản đầu tiên API được đánh dấu deprecated.

**Câu 2.** Một method có `@Deprecated(forRemoval = true)` có bị JVM vô hiệu hóa không?

**Đáp án:** Không. Nó vẫn có thể tồn tại và hoạt động; `true` là metadata thông báo ý định xóa trong tương lai.

**Câu 3.** `@deprecated` trong `/** ... */` và `@Deprecated` trước method khác nhau như thế nào?

**Đáp án:** Thẻ Javadoc mô tả lý do/hướng thay thế; annotation đánh dấu metadata để compiler và công cụ nhận biết. Nên sử dụng cả hai.

**Câu 4.** Cảnh báo `[removal]` cần được suppress bằng `"deprecation"` hay `"removal"`?

**Đáp án:** `"removal"`, nếu có lý do chính đáng để tạm suppress.

**Câu 5.** Một API phát hành từ 1.0 và deprecated từ 3.0 nên ghi thế nào?

**Đáp án:** Nếu cần ghi thời điểm ra đời, Javadoc `@since 1.0`; còn annotation `@Deprecated(since = "3.0")`. Thêm Javadoc `@deprecated` để mô tả API mới.

## Tài liệu tham khảo

- [Javadoc chuẩn Java 21: java.lang.Deprecated](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Deprecated.html).
- [Oracle Java 17 Core Libraries Developer Guide: Enhanced Deprecation](https://docs.oracle.com/en/java/javase/17/core/enhanced-deprecation1.html).

Hãy thử chỉnh `forRemoval` trong ví dụ thành `false`, biên dịch và quan sát reflection; sau đó tạo tài liệu Javadoc để so sánh hai kênh thông tin. Khi làm việc với API thực tế, hãy đọc cả annotation và lời giải thích `@deprecated` trước khi quyết định mức độ khẩn cấp và cách di chuyển.
