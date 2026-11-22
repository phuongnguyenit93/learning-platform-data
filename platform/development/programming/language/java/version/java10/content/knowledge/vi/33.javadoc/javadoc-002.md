# Vị trí và giới hạn sử dụng thẻ `{@summary ...}` trong Javadoc (Java 10+)

## 1. Vấn đề: một mô tả dài cần một câu tóm tắt rõ

Javadoc chuyển các **documentation comments** của Java thành tài liệu API: trang lớp, trang phương thức, phần tóm tắt thành viên và nội dung chi tiết. Các bảng Summary thường chỉ hiển thị một đoạn ngắn để giúp người đọc tìm API phù hợp trước khi xem toàn bộ hợp đồng của thành viên.

Nếu không chỉ định gì thêm, **standard doclet** thường lấy **câu đầu của phần main description** làm summary. Nhưng một đoạn mở đầu có dấu chấm trong tên phiên bản, chữ viết tắt, markup hoặc cách ngắt câu phức tạp có thể khiến việc cắt câu tự động không giống điều người viết mong muốn.

Từ **JDK 10**, Javadoc hỗ trợ inline tag:

```java
/**
 * {@summary Tạo một mã tham chiếu từ tiền tố và số nguyên.}
 *
 * <p>Mô tả chi tiết về thuật toán, điều kiện đầu vào và kết quả.
 *
 * @param prefix tiền tố
 * @param number số nguyên
 * @return mã tham chiếu
 */
public String format(String prefix, int number) {
    return prefix + number;
}
```

Dòng **`{@summary ...}`** ở đầu phần mô tả chính **chỉ định chính xác nội dung tóm tắt**, thay vì để standard doclet tự xác định điểm kết thúc câu đầu.

**Quy tắc quan trọng nhất của bài:**

> `{@summary ...}` là **inline tag** và chỉ có ý nghĩa **lựa chọn API summary khi nằm ở đầu main description**. Ở vị trí khác, nó không thay thế câu tóm tắt; nội dung thẻ vẫn có thể được render như văn bản thường và công cụ Javadoc có thể báo vị trí sử dụng không hợp lệ.

Thông tin trên được xác nhận trong **Oracle Java SE 26 — Documentation Comment Specification for the Standard Doclet**. Vì vậy thẻ được thêm từ Java 10 **vẫn còn được sử dụng trong JDK hiện đại**, phù hợp yêu cầu chỉ học kiến thức không legacy.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Viết đúng cú pháp **`{@summary nội dung}`**.
2. Hiểu `summary` là **inline tag**, không phải `@summary` block tag.
3. Xác định **đầu main description** nằm ở đâu trong `/** ... */`.
4. Phân biệt câu tóm tắt tự suy ra và câu tóm tắt chỉ định tường minh.
5. Biết thẻ áp dụng được cho module, package, type, constructor, method, field và các ngữ cảnh tài liệu được standard doclet hỗ trợ.
6. Biết rằng `{@summary ...}` không thay `@param`, `@return`, `@throws` hoặc mô tả chi tiết.
7. Hiểu trường hợp thẻ xuất hiện sau một câu văn không còn điều khiển API summary.
8. Nhận diện chẩn đoán `invalid use of @summary` và lỗi khi viết sai `@summary`.
9. Sử dụng `javadoc` với `-Werror` và `-Xdoclint:all` để kiểm tra tài liệu API.
10. Kiểm HTML được sinh ra và phân biệt phần **Summary** với phần **Details**.
11. Biên dịch và chạy ví dụ Java 17+, đồng thời sinh Javadoc thật.
12. Hiểu khác nhau giữa Java source compatibility và hành vi của Javadoc tool.
13. Biết giới hạn khi tài liệu dùng `///` Markdown documentation comments trên JDK mới.
14. Viết summary ngắn gọn, đúng ngữ nghĩa, có thể hiểu riêng khi hiển thị trong bảng API.
15. Phân biệt thẻ `{@summary ...}` với inline `{@return ...}` của method và các tag khác.
16. Tránh giả định mọi custom doclet, IDE hoặc JDK cũ đều xử lý thẻ như standard doclet.

## 3. Tại sao JDK 10 bổ sung `{@summary}`?

Trong **release notes Java 10**, Oracle mô tả tính năng *Comment Tag for Summary of an API Description*, liên hệ vấn đề JDK-8173425.

Trước đó, standard doclet suy ra summary từ câu đầu theo thuật toán nhận dạng câu, có thể dựa vào quy tắc đơn giản hoặc `java.text.BreakIterator` trong các chế độ phù hợp. Những thuật toán này không phải lúc nào cũng nhận ra ý định của người soạn tài liệu.

Ví dụ mô tả:

```text
Hỗ trợ dữ liệu phiên bản v1.0. Thao tác đọc dùng một đường dẫn khác.
```

Dấu chấm trong `v1.0`, chữ viết tắt, tên file, Markdown/HTML markup hoặc kiểu viết câu có thể khiến người đọc và bộ cắt câu tự động diễn giải khác nhau. Thay vì sửa nội dung bằng những cách khó hiểu chỉ để “đánh lừa” phép cắt câu, có thể viết:

```java
/**
 * {@summary Xử lý dữ liệu của một phiên bản API cụ thể.}
 * Hỗ trợ đầu vào với cách ghi phiên bản v1.0.
 * Phần còn lại giải thích hợp đồng chi tiết.
 */
public class VersionedReader {
}
```

**Ý nghĩa:** người viết chủ động xác định phần summary; phần sau thẻ vẫn là mô tả chính và có thể dài hơn.

### Điểm hiện hành

- Tính năng được **giới thiệu ở JDK 10**, không cần bật preview.
- **Oracle JDK 26 vẫn mô tả** `{@summary text}` trong tài liệu standard doclet.
- Không phải một Java keyword hay cú pháp mới cho Java compiler.
- Về bản chất đây là tính năng **công cụ tạo tài liệu**, không làm thay đổi runtime behavior.
- Không cần viết thẻ trong mọi documentation comment; nó là lựa chọn hữu ích khi muốn kiểm soát summary.
- Nếu một ứng dụng dùng JDK 17 hoặc 21 để build, thẻ vẫn được standard doclet tương ứng hỗ trợ.

## 4. Hình thức chính xác của thẻ

Cú pháp theo đặc tả hiện hành:

```text
{@summary text}
```

Thẻ có:

- `{` mở đầu.
- `@summary` là tên **inline tag**.
- Phần **text** là nội dung cần hiển thị/tóm tắt.
- `}` đóng inline tag.

Ví dụ:

```java
/**
 * {@summary Chuyển dữ liệu đầu vào thành mã định danh.}
 * Mô tả các ràng buộc, ví dụ và các trường hợp biên.
 */
public String idOf(String input) {
    return input;
}
```

**Không viết thành:**

```java
/**
 * @summary Chuyển dữ liệu thành mã định danh.
 */
```

`@summary` không phải block tag của standard doclet. Trong **thử nghiệm JDK 24**, cách viết này gây lỗi:

```text
error: incorrect use of inline tag
```

Cần giữ đúng **cặp ngoặc nhọn** của inline tag. Không nhầm với `@param`, `@return` và các block tags ở đầu dòng.

### Khoảng trắng và xuống dòng

Trong traditional doc comment, các dấu `*` ở đầu dòng và khoảng trắng mở đầu được xử lý theo quy tắc Javadoc. Ví dụ:

```java
/**
 *
 * {@summary Tạo kết quả gọn từ hai đầu vào.}
 * Phần mô tả còn lại...
 */
```

Dòng trống/whitespace ban đầu không làm nội dung đứng trước thẻ; đây vẫn là thẻ bắt đầu của main description sau khi chuẩn hóa whitespace.

**Thực hành rõ ràng nhất:** đặt `{@summary ...}` ngay ở dòng mô tả đầu tiên sau `/**` và trước mọi câu văn, HTML paragraph hoặc block tags.

## 5. Main description bắt đầu và kết thúc ở đâu?

Một Javadoc comment thường có:

```text
/**
 * [MAIN DESCRIPTION]
 * Nội dung giải thích tổng quan, có thể nhiều đoạn.
 *
 * @param name ...      <-- BLOCK TAGS
 * @return ...
 * @throws ...
 */
```

**Main description** là phần từ đầu nội dung comment đến ngay trước **block tag đầu tiên** (hoặc đến hết comment nếu không có block tag). Tài liệu Oracle 26 xác nhận **main description không thể tiếp tục sau các block tags**.

Ví dụ:

```java
/**
 * {@summary Trả về tên khách hàng theo mã.}
 *
 * <p>Chi tiết: tra cứu từ nguồn dữ liệu có sẵn.
 *
 * @param code mã khách hàng
 * @return tên khách hàng
 */
public String findName(String code) {
    return code;
}
```

Cấu trúc:

1. `{@summary Trả về tên khách hàng theo mã.}`: **đầu main description**.
2. `<p>Chi tiết...`: phần **main description** chi tiết.
3. `@param code ...`: **block tag** mở phần mô tả tham số.
4. `@return ...`: **block tag** mô tả giá trị trả về.

### Sai lầm vị trí cần tránh

```java
/**
 * @param code mã khách hàng
 * {@summary Tìm tên khách hàng theo mã.}
 * @return tên khách hàng
 */
```

Đây **không phải** cách đặt một thẻ đầu main description. Vị trí sau `@param` không đưa tag trở lại đầu comment; Javadoc có quy tắc parsing block tags riêng. Đừng đặt summary vào vùng parameters/returns rồi kỳ vọng nó điền bảng API summary.

## 6. Thẻ chỉ có ý nghĩa ở đầu main description

Đặc tả standard doclet JDK 26 viết rõ: `{@summary text}` chỉ có ý nghĩa xác định summary **khi được dùng ở đầu main description**; ở mọi nơi thẻ vẫn được render bằng cách render nội dung của nó.

So sánh:

**ĐÚNG**

```java
/**
 * {@summary Tính tổng các phần tử hợp lệ.}
 * Phương thức bỏ qua phần tử không đáp ứng chính sách lọc.
 *
 * @param a số thứ nhất
 * @param b số thứ hai
 * @return tổng hai số
 */
public int sum(int a, int b) {
    return a + b;
}
```

**SAI VỊ TRÍ**

```java
/**
 * Đây là câu đầu và đã trở thành summary tự động.
 * {@summary Nội dung đặt muộn không còn là summary chính.}
 *
 * @return số minh họa
 */
public int late() {
    return 1;
}
```

Ở ví dụ sai, thẻ không điều khiển summary vì **đã có mô tả đứng trước**. Với `javadoc` JDK 24 đã kiểm thử, trường hợp này phát sinh:

```text
warning: invalid use of @summary
```

Mặc dù nội dung của thẻ có thể vẫn xuất hiện trong phần **chi tiết**, summary của phương thức được chọn theo quy tắc mặc định từ câu đầu. Vì vậy, **đừng dựa vào việc không có lỗi biên dịch Java** để cho rằng Javadoc đã chấp nhận vị trí thẻ.

### Không đặt trước thẻ một câu dẫn hoặc tiêu đề

Ví dụ không nên:

```java
/**
 * Giới thiệu.
 * {@summary Xử lý dữ liệu trong bộ nhớ.}
 */
```

hoặc:

```java
/**
 * <p>
 * {@summary Xử lý dữ liệu trong bộ nhớ.}
 */
```

Nếu muốn `summary` có tác dụng, hãy **đặt nó trước `<p>` và trước văn bản khác**, thay vì đoán standard doclet sẽ bỏ qua các ký tự đầu dòng.

## 7. Tóm tắt tự động và tóm tắt tường minh khác nhau thế nào?

**Không dùng `{@summary}`:**

```java
/**
 * Tạo mã với tiền tố mặc định. Phần giải thích bổ sung không ở summary.
 *
 * @param number số cần thêm
 * @return mã kết quả
 */
public String defaultFormat(int number) {
    return "ref-" + number;
}
```

Standard doclet thường dùng câu đầu:

```text
Tạo mã với tiền tố mặc định.
```

**Dùng `{@summary}` ngay đầu:**

```java
/**
 * {@summary Tạo mã tham chiếu có tiền tố tùy chọn.}
 * Phương thức có nhiều quy tắc xử lý đặc biệt.
 *
 * @param prefix tiền tố của mã
 * @param number phần số
 * @return mã kết quả
 */
public String format(String prefix, int number) {
    return prefix + number;
}
```

Nội dung summary được chỉ định là:

```text
Tạo mã tham chiếu có tiền tố tùy chọn.
```

**Không cần dùng thẻ khi câu đầu ngắn gọn và rõ.** Nếu mô tả đã được viết tốt với một câu mở đầu chính xác, summary suy ra tự động thường là đủ.

### Dấu câu nằm trong nội dung thẻ

`{@summary ...}` không phải API tự suy diễn ngữ nghĩa câu và thêm dấu chấm thay người viết. Hãy viết một câu tóm tắt **đầy đủ ý, có dấu câu phù hợp**, thường kết thúc bằng dấu chấm theo phong cách Javadoc.

Nếu summary có dấu chấm trong tên `v1.0` hoặc một chuỗi mã, việc dùng thẻ giúp chỉ rõ **toàn bộ nội dung mong muốn**, thay vì mong bộ tách câu tự làm đúng.

## 8. Vị trí thẻ so với `@param`, `@return` và `@throws`

Ví dụ phương thức đầy đủ:

```java
/**
 * {@summary Ghi nội dung vào một bộ đệm.}
 * Ghi ở cuối bộ đệm, không thay đổi vùng dữ liệu hiện có.
 *
 * @param text chuỗi cần ghi
 * @return số ký tự đã ghi
 * @throws IllegalArgumentException nếu đầu vào không hợp lệ
 */
public int append(String text) {
    if (text == null) {
        throw new IllegalArgumentException("text");
    }
    return text.length();
}
```

Các loại tag đảm nhận **công việc khác nhau**:

| Tag | Vai trò | Vị trí chính |
| --- | --- | --- |
| `{@summary text}` | Chỉ định câu tóm tắt API | **Đầu main description** |
| `@param name text` | Mô tả tham số | Block tag sau main description |
| `@return text` | Mô tả giá trị trả về | Block tag của method |
| `@throws Type text` | Mô tả ngoại lệ | Block tag của method/constructor |
| `@see ...` | Tham khảo API khác | Block tag |
| `{@link ...}` | Tạo liên kết inline | Trong phần văn bản phù hợp |
| `{@code ...}` | Hiển thị code inline | Trong phần văn bản phù hợp |

**Không nghĩ summary thay thế hợp đồng của phương thức.** Nó được thiết kế ngắn và đủ nghĩa, còn chi tiết parameters, return values, error conditions và edge cases nằm ở phần nội dung phù hợp.

### Không chuyển toàn bộ tài liệu vào summary

Một summary như sau quá dài:

```java
/**
 * {@summary Phương thức này đọc tệp, kiểm tra quyền,
 * bắt mọi lỗi kết nối, ghi log, gọi lại máy chủ, xử lý khoảng trắng,
 * thiết lập bộ đệm, điều chỉnh trạng thái và hỗ trợ nhiều trường hợp...}
 */
```

Dù có thể render, người đọc phải đọc một đoạn dài trong bảng tóm tắt và khó định vị API. Hãy viết **mục đích chính** trong summary, đưa hợp đồng chi tiết vào main description và block tags.

## 9. Các loại khai báo nào sử dụng được?

Theo bảng **Where Tags Can Be Used** của Oracle JDK 26 standard doclet, `summary` có thể dùng trong các tài liệu sau:

| Ngữ cảnh | Có hỗ trợ `{@summary}`? | Ghi chú |
| --- | --- | --- |
| **Module** (`module-info.java`) | Có | Đầu main description của module |
| **Package** (`package-info.java`) | Có | Đầu mô tả package |
| **Type**: class/interface/enum/record/annotation interface | Có | API summary cho type |
| **Constructor** | Có | Tóm tắt một constructor |
| **Method** | Có | Tóm tắt phương thức |
| **Field** | Có | Tóm tắt trường |
| **Overview/other doc content** được standard doclet hỗ trợ | Có | Tùy loại trang/tài liệu, vẫn cần ở đầu main description |

**Không giới hạn tag chỉ được dùng với methods.** Bài kiểm thử thực tế bên dưới có tag hợp lệ ở **lớp, field, constructor và method**.

Vì `{@summary}` thuộc Javadoc docs, nó không được đặt tùy tiện vào chuỗi Java, comment thường `//` hoặc annotation rồi mong công cụ sinh tài liệu.

### Tài liệu của package

Ví dụ trong `package-info.java`:

```java
/**
 * {@summary Cung cấp các thành phần xử lý mã tham chiếu.}
 * Package bao gồm bộ chuyển đổi, bộ kiểm tra đầu vào
 * và các lớp phục vụ tầng ứng dụng.
 */
package com.example.reference;
```

Đây là **minh họa một file package-info.java**, không phải một phần của chương trình độc lập `SummaryTagExample.java`. Khi thật sự sử dụng, đặt file đúng thư mục tương ứng với package name.

### Tài liệu của module

Ví dụ trong `module-info.java`:

```java
/**
 * {@summary Cung cấp module xử lý tham chiếu có cấu trúc.}
 * Chi tiết về API exports và các dependency.
 */
module com.example.reference {
    exports com.example.reference;
}
```

Đây cũng là **minh họa riêng**. Module cần cấu trúc nguồn và package thực tế tương ứng; không biên dịch trực tiếp cùng class demo đặt ở default package.

## 10. Thẻ trong tài liệu của lớp và field

Một class có thể có:

```java
/**
 * {@summary Cung cấp phép chuyển đổi mã định danh.}
 *
 * <p>Tài liệu lớp giải thích các bảo đảm và các hạn chế chung.
 *
 * @since 10
 */
public final class IdFormatter {
    /**
     * {@summary Tiền tố mặc định của mã.}
     * Có thể thay đổi bằng cách truyền giá trị riêng cho mỗi lời gọi.
     */
    public static final String PREFIX = "id-";
}
```

Mô tả lớp có thể được trình bày trong bảng các loại API của package, còn field summary có thể xuất hiện trong bảng các field của class.

**Số lượng/markup của bảng HTML phụ thuộc standard doclet và bản JDK**. Không viết tooling phụ thuộc cứng vào một CSS class hoặc một chuỗi HTML nội bộ nếu chưa kiểm trên version cụ thể.

### Không cần tài liệu trùng nhau

Nếu name của field đã tự giải thích, summary nên bổ sung **ý nghĩa sử dụng**, không chỉ lặp lại identifier.

Ví dụ:

- Kém: “`PREFIX` là PREFIX.”
- Tốt: “Tiền tố mặc định của mã tham chiếu.”
- Tốt hơn nếu có ràng buộc: “Tiền tố mặc định chỉ dùng khi caller không truyền tiền tố riêng.”

## 11. Constructors và methods có phạm vi tài liệu khác nhau

Constructor có thể có `{@summary ...}` ở đầu main description như method:

```java
/**
 * {@summary Tạo bộ định dạng rỗng trạng thái.}
 * Không giữ dữ liệu giữa các lần gọi.
 */
public IdFormatter() {
}
```

Method cần mô tả hành vi:

```java
/**
 * {@summary Tạo mã từ tiền tố và số dương.}
 * Trả về chuỗi theo cú pháp tiền tố nối ngay với số.
 *
 * @param prefix tiền tố cần ghép
 * @param number số nguyên
 * @return chuỗi kết quả
 */
public String build(String prefix, int number) {
    return prefix + number;
}
```

Trong ví dụ trên, từ “số dương” là một **yêu cầu hợp đồng chỉ nên viết nếu code thực thi nó**. Mã minh họa thực tế không kiểm số dương, nên summary đúng hơn phải là “số nguyên”, hoặc cần thêm validation. Đây là nguyên tắc tài liệu API quan trọng: **summary phải chính xác so với implementation**, không được dùng từ ngữ vượt quá cam kết của phương thức.

### Một câu summary hay phải trả lời được

- API làm gì?
- Điều kiện áp dụng chính là gì (nếu quan trọng)?
- Người đọc có thể quyết định nên mở phần Details không?

Summary **không** cần giải thích toàn bộ implementation, performance hoặc stack trace.

## 12. Main description không tiếp tục sau block tag

Xét ví dụ:

```java
/**
 * {@summary Xác nhận mã định danh.}
 * Chi tiết của thuật toán kiểm tra.
 *
 * @param code mã định danh
 * @return kết quả kiểm tra
 */
```

Câu tóm tắt nằm trước `@param`.

Nếu viết:

```java
/**
 * @param code mã định danh
 * {@summary Xác nhận mã định danh.}
 * @return kết quả kiểm tra
 */
```

thì **main description đã kết thúc trước @param**. Không thể mở lại nó chỉ vì đặt một inline tag ở dòng sau.

**Giới hạn thực tế:** `{@summary ...}` không dùng để mô tả tham số hay return value; các mô tả đó có tag riêng. Vì vậy không đặt summary vào `@param`/`@return` với hy vọng nó đại diện cho cả method.

### Thứ tự hợp lý

Trong code review, ưu tiên:

1. `{@summary ...}` ngay đầu comment.
2. Mô tả main description chi tiết.
3. Một dòng trống.
4. `@param` cho các tham số.
5. `@return` nếu có giá trị trả về.
6. `@throws` cho những ngoại lệ đáng tài liệu hóa.
7. `@since`, `@see` và những block tags khác khi hữu ích.

Thứ tự tuyệt đối giữa mọi block tag không phải bản chất của `{@summary}`; bản chất là **vùng main description đứng trước block tags**.

## 13. Không nhầm `{@summary}` với `{@return}` inline

Standard doclet hiện đại hỗ trợ thêm dạng **inline**:

```text
{@return description}
```

Theo Oracle JDK 26, inline `{@return ...}`:

- Dùng **chỉ cho method**.
- Chỉ được đặt **ở đầu main description** của method.
- Đồng thời cung cấp phần mô tả của **Returns** và một câu đầu có dạng “Returns ...” trong locale mặc định phù hợp.

Trong khi đó `{@summary ...}`:

- Dùng cho nhiều ngữ cảnh API, không chỉ methods.
- Chỉ định summary cụ thể.
- **Không** tự tạo block `@return` hay thông tin returns.

**Khi method cần cả summary tùy chỉnh và mô tả return**, dùng:

```java
/**
 * {@summary Đọc mã tham chiếu của khách hàng.}
 * Phần chi tiết về nguồn dữ liệu và lỗi.
 *
 * @return mã tham chiếu, hoặc chuỗi rỗng nếu chưa có
 */
public String readId() {
    return "";
}
```

Không cố đặt cả hai inline tags `{@summary ...}` và `{@return ...}` vào cùng **vị trí đầu tiên** của một mô tả; mỗi tag có quy tắc placement riêng, nên cách rõ ràng là **chọn một để mở đầu và sử dụng block `@return` nếu chọn summary**.

**Chú ý:** Dạng inline `{@return}` được bổ sung vào Javadoc sau thời Java 10; việc bài nhắc đến nó chỉ nhằm tránh nhầm trên **JDK hiện đại**, không buộc chương trình minh họa phải dùng.

## 14. Tương tác với các inline tags khác

Thẻ `{@summary}` nằm trong nhóm inline tags, cùng các tag như:

- `{@code ...}`: trình bày code trong văn bản.
- `{@literal ...}`: nội dung literal.
- `{@link ...}`: liên kết đến một API khác.
- `{@index ...}`: đánh dấu mục cho chỉ mục Javadoc.
- `{@inheritDoc}`: lấy tài liệu từ declaration được override phù hợp.

**Chúng không thay thế vai trò của nhau**. Nếu summary có liên kết hoặc mã, cần tuân thủ cú pháp inline tags/HTML được standard doclet chấp nhận.

Ví dụ đơn giản, an toàn:

```java
/**
 * {@summary Tạo mã phân loại đơn giản.}
 * Xem {@link java.lang.String} về chuỗi đầu ra.
 */
```

Ở đây `{@summary ...}` nằm trước, còn `{@link ...}` nằm trong phần chi tiết. Dùng thẻ liên kết không tự tạo câu summary.

### Tóm tắt không được biến thành đoạn mô tả kỹ thuật rất dài

Nội dung thẻ có thể chứa markup hợp lệ, nhưng **bảng Summary phải dễ đọc**. Tránh nhồi một code snippet, HTML table hoặc nhiều đoạn dài vào summary. Dùng `{@code ...}`/`{@link ...}` vừa đủ và đặt ví dụ ở phần chi tiết.

### Khi method kế thừa tài liệu

Các method override có cơ chế `{@inheritDoc}` và quy tắc kế thừa documentation riêng. Đừng giả định việc thêm `{@summary}` vào một method con tự động kế thừa mọi mô tả về `@param`, `@return` hoặc `@throws`. Kiểm Javadoc generated output của cả declaration và hierarchy khi document overrides.

## 15. Ví dụ Java 17+ độc lập, biên dịch được

Tạo file **`SummaryTagExample.java`**:

```java
/**
 * {@summary Minh họa cách khai báo câu tóm tắt API một cách tường minh.}
 *
 * <p>Phần mô tả chi tiết giải thích vai trò của lớp và các phương thức.
 *
 * @since 10
 */
public final class SummaryTagExample {
    /**
     * {@summary Tiền tố mặc định của mã tham chiếu.}
     * Giá trị này được dùng khi không truyền tiền tố riêng.
     */
    public static final String DEFAULT_PREFIX = "ref-";

    /**
     * {@summary Tạo đối tượng trình diễn Javadoc.}
     * Constructor không giữ trạng thái.
     */
    public SummaryTagExample() {
    }

    /**
     * {@summary Ghép tiền tố và số nguyên thành một mã tham chiếu.}
     * Phần mô tả chi tiết có thể có nhiều câu.
     * Summary vẫn chỉ là nội dung thẻ ở đầu.
     *
     * @param prefix tiền tố cần ghép
     * @param number số cần biểu diễn
     * @return chuỗi gồm tiền tố và số
     */
    public String format(String prefix, int number) {
        return prefix + number;
    }

    /**
     * Tạo mã với tiền tố mặc định. Mô tả thêm không thuộc câu tóm tắt.
     *
     * @param number số cần biểu diễn
     * @return mã tham chiếu dùng tiền tố mặc định
     */
    public String defaultFormat(int number) {
        return format(DEFAULT_PREFIX, number);
    }

    /**
     * Chạy ví dụ và in kết quả.
     *
     * @param args đối số dòng lệnh, không sử dụng
     */
    public static void main(String[] args) {
        var example = new SummaryTagExample();
        System.out.println("explicit=" + example.format("order-", 12));
        System.out.println("implicit=" + example.defaultFormat(7));
        System.out.println("summaryChangesRuntime=false");
    }
}
```

Chương trình:

- Có `{@summary}` ở **đầu main description** của **class, field, constructor và method `format`**.
- Có method `defaultFormat` **không dùng thẻ**, để cho Javadoc chọn câu đầu tự động.
- Dùng `@param` và `@return` cho những mô tả chi tiết còn cần thiết.
- Không chứa API preview/legacy hoặc hành vi phụ thuộc Java 10 cũ.
- Phần Java source không hề đọc summary tags để tính toán; Javadoc là **tooling documentation**, không phải logic runtime.

**Biên dịch với JDK 17+:**

```bash
javac --release 17 -encoding UTF-8 SummaryTagExample.java
```

**Chạy:**

```bash
java SummaryTagExample
```

**Stdout chính xác:**

```text
explicit=order-12
implicit=ref-7
summaryChangesRuntime=false
```

Giải thích:

- `explicit=order-12`: `format("order-",12)` ghép hai phần.
- `implicit=ref-7`: `defaultFormat(7)` dùng hằng `DEFAULT_PREFIX`.
- `summaryChangesRuntime=false`: minh họa thẻ chỉ ảnh hưởng **tài liệu sinh ra**, không sửa cách JVM chạy phương thức.

Tất cả ba dòng output đã được đối chiếu khi thực thi lớp được biên dịch bằng `javac --release 17` trên HotSpot JDK 24.

## 16. Sinh Javadoc thực tế bằng standard doclet

Trong thư mục chứa `SummaryTagExample.java`, chạy:

```bash
javadoc -quiet -Werror -Xdoclint:all \
        -encoding UTF-8 -charset UTF-8 \
        -d docs SummaryTagExample.java
```

Trên **PowerShell**, có thể nhập trên **một dòng**:

```powershell
javadoc -quiet -Werror -Xdoclint:all -encoding UTF-8 -charset UTF-8 -d docs SummaryTagExample.java
```

Lưu ý:

- `-d docs`: thư mục output tài liệu.
- `-encoding UTF-8`: charset cho Java source documentation.
- `-charset UTF-8`: khai báo encoding của HTML output.
- `-quiet`: giảm các thông báo tiến trình không cần thiết.
- `-Xdoclint:all`: bật bộ kiểm tra tài liệu.
- `-Werror`: coi các warnings mà Javadoc báo là lỗi, hữu ích cho pipeline CI.
- `SummaryTagExample.java`: source file dùng để tạo tài liệu.

**Kết quả kiểm thử:** với JDK 24, lệnh `javadoc` trên **chạy thành công cùng `-Werror`**, không có warnings/errors trong ví dụ hợp lệ.

### Đọc file HTML sinh ra

Mở:

```text
docs/SummaryTagExample.html
```

Trong phần **Method Summary**, tìm:

```text
Ghép tiền tố và số nguyên thành một mã tham chiếu.
Tạo mã với tiền tố mặc định.
```

Mô tả chi tiết:

```text
Phần mô tả chi tiết có thể có nhiều câu.
Mô tả thêm không thuộc câu tóm tắt.
```

không bị kéo theo vào **Method Summary**, nhưng có mặt trong nội dung chi tiết của từng method.

Trong phần **Field Summary**, tìm:

```text
Tiền tố mặc định của mã tham chiếu.
```

Đây là một cách kiểm trực quan rằng thẻ `{@summary ...}` đã phát huy tác dụng chứ không chỉ hiện trong HTML như một chuỗi văn bản.

**Không phụ thuộc cứng vào tên CSS class/id HTML của JDK 24** trong một hệ thống tự viết; cấu trúc HTML có thể thay đổi giữa các bản standard doclet. Khi automation cần parse docs, kiểm đúng version/build và dùng những selector đã xác minh.

## 17. Thử nghiệm sai vị trí: warning có ý nghĩa gì?

Một ví dụ **cố ý sai**:

```java
/**
 * Câu đầu xuất hiện trước thẻ. {@summary Thẻ đặt muộn không làm tóm tắt.}
 *
 * @return số nguyên
 */
public static int late() {
    return 1;
}
```

Với standard doclet JDK 24 đã kiểm thử, chương trình báo:

```text
warning: invalid use of @summary
```

Điều này minh họa chính xác quy tắc trong spec: `{@summary}` không còn xác định summary nếu xuất hiện **sau** phần văn bản đầu main description.

Với `-Werror`, warning này làm **bước generate Javadoc thất bại**; pipeline không nên coi tài liệu hợp lệ.

### Tại sao nội dung thẻ có thể vẫn xuất hiện?

Đặc tả nói tag luôn được render bằng cách render text của nó. Nhưng **render text** và **chỉ định summary** là hai chuyện khác:

- Nằm đúng đầu → điều khiển summary, đồng thời hiển thị nội dung.
- Nằm ở vị trí khác → có thể hiển thị text trong chi tiết, **không** điều khiển summary và có thể bị báo invalid use.

Do đó không nên chỉ mở trang chi tiết, thấy nội dung thẻ rồi kết luận nó đã thay summary.

### Kết luận từ kiểm thử

Ví dụ sai vị trí trên **không** nằm trong file Java hợp lệ `SummaryTagExample.java`. Đặt nó vào source chính rồi bật `-Werror` sẽ làm pipeline báo lỗi, đi ngược mục tiêu có một demo sinh Javadoc sạch.

## 18. Nhầm lẫn khác: dùng `@summary` như block tag

Một ví dụ **cố ý sai**, không phải code để copy:

```java
/**
 * Dòng mô tả đầu tiên.
 *
 * @summary Đây không phải cách dùng hợp lệ
 * @return số nguyên
 */
public static int wrongBlock() {
    return 2;
}
```

`@summary` nằm ở đầu dòng nhưng **không có cặp ngoặc** `{...}` của inline tag.

Trên standard doclet JDK 24 đã kiểm thử, trường hợp này báo:

```text
error: incorrect use of inline tag
```

**Cách sửa:**

```java
/**
 * {@summary Tạo một số nguyên minh họa.}
 *
 * @return số nguyên
 */
public static int correct() {
    return 2;
}
```

Phân biệt nhanh:

| Cách viết | Kết luận |
| --- | --- |
| `{@summary Nội dung.}` **đầu main description** | Đúng |
| `{@summary Nội dung.}` **sau câu đầu** | Sai vị trí; không chọn summary |
| `@summary Nội dung.` ở đầu dòng | Sai cú pháp; không phải block tag |
| `{@summary ...}` sau `@param` | Không phải đầu main description |
| Mô tả đầu có câu rõ ràng, **không có thẻ** | Hợp lệ; summary tự động |

## 19. Cách tổ chức tài liệu chuẩn cho một API công khai

Một tài liệu method thường dễ đọc theo thứ tự:

```java
/**
 * {@summary Chuyển một chuỗi đầu vào thành mã đã chuẩn hóa.}
 *
 * <p>Hợp đồng: bỏ khoảng trắng đầu/cuối và thay các dấu phân cách
 * theo quy ước hệ thống. Không xử lý dữ liệu null.
 *
 * @param input chuỗi đầu vào, không được null
 * @return mã sau khi chuẩn hóa
 * @throws IllegalArgumentException nếu input không hợp lệ
 * @since 10
 */
```

Đây là **minh họa documentation comment**, chưa có method declaration/implementation, nên không phải Java source độc lập. Nó thể hiện cách chia:

- **Summary**: một câu nêu mục đích API.
- **Main description**: hành vi, giới hạn, quy tắc, ví dụ.
- **Parameters/returns/exceptions**: hợp đồng theo từng thành phần.
- **Metadata**: `@since` và những thông tin bổ sung hữu ích.

### Viết summary đủ nghĩa khi đứng một mình

Trong bảng API, một summary có thể đứng cạnh signature mà không hiện toàn bộ mô tả dài. Tránh:

- “Đọc ở dưới.”
- “Làm công việc này.”
- “Xử lý theo cách bình thường.”
- “Phương thức mới.”

Nên viết:

- “Tạo mã tham chiếu bằng cách ghép tiền tố với số nguyên.”
- “Trả về kích thước bộ đệm hiện tại theo số ký tự.”
- “Kiểm tra mã đầu vào theo các quy tắc đã khai báo.”

Không đề cập hành vi mà implementation **không bảo đảm**, kể cả khi muốn câu văn nghe mạnh mẽ hơn.

## 20. Dấu chấm, viết tắt, câu đầu và nhu cầu dùng thẻ

Một vấn đề Javadoc truyền thống là việc phân biệt **dấu chấm kết thúc câu** với dấu chấm nằm trong:

- Tên phiên bản (`v1.0`, `2.3.4`).
- Tên miền (`example.com`).
- Tên tệp (`config.properties`).
- Chữ viết tắt (`e.g.`, `i.e.`), phụ thuộc locale.
- HTML elements hoặc văn bản được markup.
- Các biểu thức code chứa dấu chấm và khoảng trắng.

Javadoc có thể chọn câu đầu theo thuật toán tương ứng, nhưng **không nên viết documentation dựa trên giả định mọi dấu chấm đều được nhận diện đúng**.

`{@summary ...}` cho người viết ranh giới rõ ràng, đặc biệt khi phần giải thích phải bắt đầu bằng những dữ liệu có định dạng phức tạp.

Ví dụ:

```java
/**
 * {@summary Đọc cấu hình cho một phiên bản ứng dụng.}
 * Hệ thống hỗ trợ tên file dạng config.v1.0.properties.
 * Phần còn lại mô tả quy tắc tìm file và xử lý lỗi.
 */
```

Summary vẫn do **thẻ** xác định, không phụ thuộc tên file có nhiều dấu chấm.

### Không biến thẻ thành một thủ thuật để giấu nội dung sai

Nếu một API chưa có hợp đồng rõ ràng, việc viết summary hay không giải quyết vấn đề. Một summary tường minh tốt cần dựa trên **ngữ nghĩa API đúng**, không che giấu exception, tác dụng phụ hoặc behavior breaking quan trọng.

## 21. `{@summary}` trong Markdown documentation comments hiện đại

Từ **JDK 23**, Javadoc có thêm **Markdown documentation comments** sử dụng tiền tố `///` cho từng dòng, bên cạnh traditional `/** ... */`.

Các inline tags (gồm `{@summary ...}`) vẫn có thể được sử dụng trong Markdown documentation comments theo standard doclet hiện hành, miễn là thẻ ở **đầu main description** khi muốn điều khiển summary.

Ví dụ minh họa **JDK 23+**:

```java
/// {@summary Cung cấp tiện ích mã hóa dữ liệu ngắn.}
///
/// Giải thích thêm bằng cú pháp **Markdown**.
public final class MarkdownSummaryExample {
}
```

**Lưu ý tương thích:** ví dụ `///` cần toolchain JDK hiện đại hỗ trợ Markdown documentation comments để được nhận diện là Javadoc. Nó **không phải** thay thế cho ví dụ truyền thống đã được biên dịch với `--release 17`.

Trong một dự án cần chạy JDK 17, hãy ưu tiên traditional Javadoc `/** ... */` như chương trình đầy đủ ở mục 15. Đừng lấy một tính năng của JDK 23 rồi tuyên bố đã có ở Java 10.

### Dùng markup trong Markdown comments

Theo đặc tả, inline tags được nhận diện ngoài code spans/fenced code blocks. Nếu viết chuỗi `{@summary ...}` **bên trong code span** hoặc code fence Markdown thì đó là **văn bản literal minh họa**, không được standard doclet coi là thao tác tạo summary.

Muốn tag hoạt động, đặt nó như **markup Javadoc thật ở đầu comment**, không đặt trong một khối code ví dụ.

## 22. Các giới hạn của API, tool và doclet

`{@summary}` không phải một Java language feature có tác động đến bytecode/runtime. Phạm vi hỗ trợ phụ thuộc công cụ đọc Javadoc comments.

| Tình huống | Điều cần biết |
| --- | --- |
| `javac` biên dịch source Java | Thẻ trong comment không thay hành vi code |
| Standard `javadoc` JDK 10+ | Nhận `{@summary}` theo quy tắc của standard doclet |
| Javadoc JDK 26 | Vẫn tài liệu hóa thẻ và giới hạn vị trí |
| JDK cũ hơn Java 10 | Không mặc định hỗ trợ; cần đúng toolchain |
| Custom doclet hoặc IDE parser | Có thể có cách hiểu/hiển thị khác |
| Java `//` comment thông thường | Không phải Javadoc comment |
| String literal có chữ `{@summary}` | Không phải documentation tag |
| `///` Markdown comment trên JDK hiện đại | Có thể hỗ trợ; cần đúng JDK/doclet |
| Code fence Markdown trong doc comment | Inline tags bên trong fence là literal |

### Cách chọn phiên bản Javadoc khi build

- Dùng **JDK toolchain cố định** cho build tài liệu.
- Nếu cung cấp source cho nhiều JDK, xác định **minimum Javadoc tool version**.
- Kiểm `javadoc -version`/`java -version` trong pipeline khi cần.
- Không giả định `javac --release 17` khiến **mọi** bản `javadoc` sinh HTML giống JDK 17; `--release` điều khiển tương thích biên dịch của `javac`, còn standard doclet do tool JDK đang chạy quyết định.

Tài liệu do JDK 17 và JDK 26 sinh ra có thể khác **HTML structure, styling và tính năng doclet**, dù cùng tôn trọng ngữ nghĩa của thẻ summary.

## 23. Kiểm thử Javadoc trong CI/CD

Một pipeline đơn giản:

```bash
javac --release 17 -encoding UTF-8 SummaryTagExample.java

javadoc -quiet -Werror -Xdoclint:all \
        -encoding UTF-8 -charset UTF-8 \
        -d docs SummaryTagExample.java
```

**Ý nghĩa của hai bước:**

1. `javac` kiểm Java source có thể biên dịch theo target API/bytecode tương ứng.
2. `javadoc` kiểm Javadoc comments và tạo tài liệu.

Một file có thể **biên dịch Java thành công** nhưng **sinh Javadoc thất bại** vì một thẻ sai. Đây là lý do cần cả hai bước khi dự án coi tài liệu API là phần của chất lượng release.

### Khi nào `-Werror` hữu ích?

Trong JDK 24 đã thử, việc đặt sai vị trí `{@summary}` có thể chỉ tạo **warning**. Nếu build không coi warnings là failures, tài liệu vẫn có thể được generate nhưng summary sai ý định. Dùng `-Werror` giúp CI không bỏ qua những cảnh báo ấy.

**Không phải mọi warning đều bắt nguồn từ summary.** `-Xdoclint:all` còn giúp phát hiện issues như thiếu hoặc sai `@param`, `@return`, malformed HTML, v.v. Khi build fail, đọc toàn bộ diagnostic và sửa theo loại lỗi, không tắt doclint mặc định.

### Tại sao không tắt doclint để “chạy xanh”?

Tắt `doclint` hoặc `-Werror` chỉ che đi vấn đề trình bày/hợp đồng của tài liệu. Đối với API công khai, summary sai có thể khiến người dùng hiểu nhầm hoặc chọn nhầm overload. Hãy sửa tag/position thay vì coi tài liệu chỉ là phụ.

## 24. Những sai lầm phổ biến về vị trí thẻ

### Lỗi A — Viết `@summary` giống `@param`

Sai cú pháp. **Sửa:** dùng `{@summary ...}`.

### Lỗi B — Đặt thẻ sau câu đầu

Không còn chọn summary và có thể bị warning. **Sửa:** chuyển lên đầu main description.

### Lỗi C — Đặt `<p>` trước thẻ

Không nên nếu muốn thẻ là phần mở đầu. **Sửa:** đặt `{@summary ...}` trước paragraph markup.

### Lỗi D — Đặt thẻ trong `@return` hoặc `@param`

Sai phạm vi. **Sửa:** đặt ở main description; mô tả return/param bằng block tag riêng.

### Lỗi E — Nghĩ thẻ chỉ dùng cho method

Sai. Standard doclet hỗ trợ module/package/type/constructor/method/field và ngữ cảnh tài liệu phù hợp.

### Lỗi F — Nghĩ phải dùng thẻ cho mọi API

Không cần. Nếu câu đầu tự nhiên làm summary tốt, Javadoc có thể tự chọn.

### Lỗi G — Nghĩ `{@summary}` đổi output runtime

Sai. Comment dùng cho documentation tooling, không đổi thuật toán Java.

### Lỗi H — Chép toàn bộ mô tả dài vào summary

Khiến bảng Summary khó quét. **Sửa:** một câu rõ mục đích; chi tiết chuyển xuống dưới.

### Lỗi I — Dùng summary để thay `@param`/`@return`

Không thay được hợp đồng các tham số/giá trị trả về. **Sửa:** mỗi phần có đúng tag.

### Lỗi J — Tưởng thẻ hiện trong Details là đã điều khiển summary

Không chắc. Thẻ sai vị trí có thể vẫn render nội dung trong Details. **Sửa:** xem đúng bảng Summary trong HTML.

### Lỗi K — Chỉ chạy `javac`, không chạy `javadoc`

Bỏ lỡ diagnostics của doclet. **Sửa:** có bước generate docs, ưu tiên `-Werror`.

### Lỗi L — Tưởng Markdown code fence cũng parse Javadoc tags

Sai. Tags trong code fences/spans của Markdown doc comments là literal. **Sửa:** đặt tag ở vị trí cú pháp đúng ngoài code block.

### Lỗi M — Coi JDK 23 `///` là tính năng JDK 10

Sai về lịch sử. **Sửa:** phân biệt Javadoc summary tag JDK 10 và Markdown doc comments JDK 23+.

### Lỗi N — Viết summary khẳng định những điều code không làm

Sai về nội dung. **Sửa:** so khớp hành vi Java, tests và exceptions.

### Lỗi O — Phụ thuộc CSS/id HTML vĩnh viễn

Standard doclet có thể đổi giao diện qua các bản. **Sửa:** xác minh toolchain và output thực tế.

### Lỗi P — Nghĩ custom doclet chắc chắn hỗ trợ như standard doclet

Không có cam kết chung. **Sửa:** kiểm loại doclet/IDE thực sự trong build.

## 25. Checklist code review cho `{@summary}`

1. **Đúng cú pháp `{@summary ...}`**, không phải `@summary`?
2. **Nằm đầu main description**?
3. Không có câu văn, `<p>` hoặc block tag đứng trước?
4. Có chính xác **một ý chính** thay vì nhiều đoạn khó quét?
5. Câu summary có đầy đủ ngữ nghĩa và dấu câu hợp lý?
6. Không khẳng định behavior khác với Java source?
7. Với method, `@param` đã mô tả đủ tham số cần thiết?
8. Với method trả giá trị, `@return` có mô tả output?
9. Với exceptions, `@throws` có phản ánh contract?
10. Với type, class-level summary có mô tả mục đích type?
11. Với field, summary mô tả ý nghĩa thay vì lặp identifier?
12. Với constructor, summary nói rõ đối tượng được tạo ra?
13. Với package/module, tài liệu nằm đúng file/declaration?
14. Có cần tag hay câu đầu tự động đã đủ rõ?
15. Có chứa chữ viết tắt/dấu chấm khiến summary tự động không ổn?
16. Không đặt `{@summary}` trong `@param`, code span hoặc code fence?
17. Nếu có `{@return ...}` inline, đã tránh hai tag tranh vị trí đầu?
18. Không nhầm Javadoc với comment `//` thường?
19. Có kiểm toolchain đủ mới để hỗ trợ tag?
20. Có chạy `javac` và `javadoc -Xdoclint:all -Werror`?
21. Có xem đúng **Summary table** thay vì chỉ Details?
22. Có xác minh output sau khi đổi JDK/doclet?
23. Có loại bỏ warnings về `invalid use of @summary`?
24. Có đảm bảo không copy những trường hợp **cố ý sai** vào code production?
25. Nội dung summary có giúp người dùng chọn API nhanh không?

## 26. Bài tập áp dụng

**Bài 1.** Cho comment:

```java
/**
 * {@summary Tìm mã theo khóa.}
 * Chi tiết về cách tìm và lỗi.
 * @param key khóa tìm kiếm
 * @return mã tương ứng
 */
```

Thẻ có ở đúng vị trí không?

**Bài 2.** Cho comment:

```java
/**
 * Mô tả chung. {@summary Tìm mã theo khóa.}
 */
```

Câu nào được standard doclet chọn làm summary?

**Bài 3.** Có được viết `@summary Mô tả.` ở đầu dòng không?

**Bài 4.** Main description có thể tiếp tục sau `@return` không?

**Bài 5.** Nếu không dùng `{@summary}`, Javadoc chọn summary như thế nào?

**Bài 6.** Thẻ có dùng cho field không?

**Bài 7.** Thẻ có dùng cho package/module không?

**Bài 8.** Một summary dùng để thay `@throws` được không?

**Bài 9.** Nếu `javadoc` cảnh báo thẻ không hợp lệ nhưng `javac` thành công, code có cần sửa không?

**Bài 10.** Mô tả có nhiều dấu chấm trong tên file, vì sao `{@summary}` hữu ích?

**Bài 11.** `{@summary}` có làm phương thức chạy nhanh hơn không?

**Bài 12.** Khi muốn mô tả return và summary riêng, nên dùng tag nào?

**Bài 13.** `///` Markdown doc comment có phải đã có trong Java 10 không?

**Bài 14.** Một `{@summary}` nằm trong Markdown code fence có được parse như tag không?

**Bài 15.** Nội dung của thẻ sai vị trí có thể vẫn hiển thị trong Details không?

**Bài 16.** Vì sao nên bật `-Werror` trong CI tạo API docs?

**Bài 17.** Nếu có cả class summary và method summary, mỗi thẻ đặt ở đâu?

**Bài 18.** Có nên viết summary “Xử lý theo các điều kiện nêu sau” không?

**Bài 19.** Khi đổi JDK 17 sang JDK 26, HTML output có bắt buộc giống hệt không?

**Bài 20.** Nếu source đã có câu đầu rõ nghĩa, có bắt buộc thêm thẻ mới không?

**Đáp án:**

1. Có, thẻ mở đầu main description.
2. Câu đầu “Mô tả chung.” được chọn; tag đặt muộn không thay summary và có thể gây warning.
3. Không. Cú pháp đúng là **inline `{@summary ...}`**.
4. Không. Main description kết thúc trước block tag đầu tiên.
5. Theo cơ chế xác định câu đầu của main description.
6. Có, standard doclet hỗ trợ field.
7. Có, trong documentation comment của package/module phù hợp.
8. Không; `@throws` có vai trò riêng.
9. Có; `javac` không thay thế Javadoc validation.
10. Giúp tự chỉ định ranh giới câu tóm tắt.
11. Không; thẻ không thay hành vi bytecode/runtime.
12. `{@summary ...}` ở đầu và `@return ...` ở block tags.
13. Không; hỗ trợ Markdown documentation comments được bổ sung sau Java 10 (JDK 23).
14. Không, đó là literal text của Markdown code block.
15. Có; render text không đồng nghĩa chọn nó làm summary.
16. Để warnings như sai vị trí thẻ làm pipeline thất bại.
17. Ở đầu **main description của từng declaration** tương ứng.
18. Không nên; summary không cung cấp chức năng chính khi đứng một mình.
19. Không. Doclet version có thể thay giao diện/HTML structure.
20. Không; default first-sentence summary thường đủ.

## 27. Tổng kết

- **Java 10 bổ sung inline tag `{@summary text}`** để chỉ định summary của API description.
- **Thẻ phải ở đầu main description** mới có ý nghĩa chọn summary; khoảng trắng ban đầu khác với văn bản/paragraph thực sự đứng trước thẻ.
- **`@summary` không phải block tag hợp lệ**; cần dấu ngoặc `{...}`.
- Nếu thẻ đặt muộn, nó có thể vẫn render text nhưng không thay summary và Javadoc hiện đại có thể cảnh báo `invalid use of @summary`.
- Không dùng thẻ thì Javadoc **suy ra câu đầu** của main description.
- Standard doclet cho phép thẻ ở **module, package, type, constructor, method, field** và những ngữ cảnh tài liệu thích hợp.
- Thẻ **không thay `@param`, `@return`, `@throws`**, không sửa Java behavior và không phải một cách thay cho tài liệu chi tiết.
- Java 17+ demo và `javadoc -Xdoclint:all -Werror` đã xác minh cả summary tường minh và tự động trong HTML.
- **Markdown `///`** là tính năng JDK mới hơn, không nên gán cho Java 10; thẻ summary vẫn hoạt động trong phạm vi doclet hỗ trợ.
- Chọn câu ngắn, đầy đủ nghĩa và chính xác so với code; giữ Javadoc warnings bằng không trong API release.

## 28. Nguồn tham khảo chính thức

1. [Oracle Java SE 26 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html): `{@summary text}` chỉ có ý nghĩa ở đầu main description; bảng ngữ cảnh hỗ trợ; các quy tắc inline/block tags.
2. [Oracle Java SE 10 — Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): tính năng *Comment Tag for Summary of an API Description*, JDK-8173425.
3. [OpenJDK JDK-8173425 — Javadoc needs a new tag to specify the summary](https://bugs.openjdk.org/browse/JDK-8173425): động cơ thêm tag.
4. [Oracle Java SE 26 — The javadoc Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html): `-encoding`, `-charset`, `-d`, `-Werror` và tạo API documentation.
5. [Oracle Java SE 26 — Documentation Comment Overview](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html#documentation-comments): main description, block tags, inline tags và traditional/Markdown documentation comments.
6. [OpenJDK JEP 467 — Markdown Documentation Comments](https://openjdk.org/jeps/467): hỗ trợ `///` từ JDK 23, để phân biệt với `{@summary}` của JDK 10.
7. [Oracle Java SE 26 — DocLint](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javadoc.html): kiểm tra Javadoc có chất lượng và xử lý diagnostics.
8. [Oracle Java SE 26 — `{@return}` inline tag](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html#return): so sánh placement và vai trò khác `{@summary}`.
