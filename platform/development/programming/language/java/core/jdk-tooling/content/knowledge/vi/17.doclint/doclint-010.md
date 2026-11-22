# Kiểm thử documentation bằng Doclint

**Doclint** là bộ kiểm tra chất lượng documentation comments của công cụ `javadoc`. Nó phân tích cú pháp Javadoc, các tag, liên kết tham chiếu đến API và HTML được nhúng trong comment, đồng thời có thể phát hiện một số vấn đề về khả năng truy cập (accessibility) và tài liệu còn thiếu.

Doclint giúp phát hiện lỗi trong tài liệu ngay ở bước build. Khi kết hợp với `-Werror`, nhóm phát triển có thể yêu cầu bước tạo Javadoc thất bại nếu còn warning, từ đó đưa chất lượng documentation vào CI.

Doclint kiểm tra phần tài liệu và các tham chiếu mà Javadoc có thể phân tích. Nó không chứng minh nội dung mô tả đúng về nghiệp vụ, không chạy các ví dụ Java và không thay thế unit test hoặc kiểm tra HTML trên trình duyệt.

## 1. Vì sao cần kiểm thử documentation?

Tài liệu API là một phần của giao diện mà lập trình viên khác dựa vào. Một comment sai có thể khiến người dùng gọi method không đúng, hiểu nhầm điều kiện đầu vào hoặc bỏ qua exception quan trọng.

Các lỗi documentation thường gặp:

- Sai tên tham số trong `@param`.
- Thiếu mô tả giá trị trả về hoặc exception.
- `{@link}` trỏ đến method hoặc class không tồn tại.
- Dùng sai cú pháp block tag hoặc inline tag.
- HTML thiếu thẻ đóng, lồng thẻ sai hoặc dùng thuộc tính không hợp lệ.
- Nội dung HTML thiếu thông tin hỗ trợ accessibility.
- API public có comment quá sơ sài hoặc chưa có tài liệu.
- Thay đổi chữ ký method nhưng không cập nhật Javadoc tương ứng.

Nếu chỉ mở một vài trang HTML để xem thủ công, những lỗi tham chiếu và tag có thể bị bỏ sót. Doclint tự động kiểm tra nhiều lỗi này mỗi khi tài liệu được tạo.

## 2. Doclint hoạt động như thế nào?

Khi chạy `javadoc`, công cụ đọc mã nguồn, tìm documentation comments và phân tích các tag cùng HTML bên trong. Doclint kiểm tra cấu trúc và những tham chiếu mà nó có thể phân giải.

Quy trình tổng quát:

1. Javadoc chọn các source file, package hoặc module.
2. Công cụ phân tích khai báo class, method, field và doc comment.
3. Doclint kiểm tra syntax, reference, HTML, accessibility và missing documentation theo nhóm được bật.
4. Javadoc hiển thị error hoặc warning.
5. Nếu không có lỗi chặn, standard doclet tạo tài liệu HTML.
6. Tùy chọn `-Werror` có thể biến warning thành lỗi của lần chạy.

Ví dụ:

```bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src com.example.api
```

Lệnh này yêu cầu kiểm tra tất cả nhóm Doclint và kết thúc thất bại nếu còn warning.

## 3. Các nhóm kiểm tra Doclint

Javadoc cung cấp các nhóm kiểm tra sau:

| Nhóm | Nội dung kiểm tra | Ví dụ vấn đề |
| --- | --- | --- |
| `accessibility` | Một số yêu cầu accessibility của nội dung HTML | Hình ảnh thiếu mô tả thay thế hoặc cấu trúc nội dung khó tiếp cận |
| `html` | Cú pháp và cấu trúc HTML trong doc comment | Thẻ không hợp lệ, lồng thẻ sai hoặc thiếu thẻ đóng |
| `reference` | Tham chiếu đến class, method, field và thành phần API | `{@link}` trỏ đến method không tồn tại |
| `syntax` | Cú pháp documentation comment và cách dùng tag | Tag sai vị trí, sai cấu trúc hoặc sai định dạng |
| `missing` | Tài liệu hoặc tag bắt buộc theo các kiểm tra missing | Thành viên được tài liệu hóa nhưng thiếu comment hoặc tag tương ứng |

Có thể bật từng nhóm để điều tra:

```bash
javadoc -Xdoclint:html -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:reference -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:syntax -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:accessibility -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:missing -d build/docs -sourcepath src com.example.api
```

Khi muốn kiểm tra toàn diện, dùng `-Xdoclint:all`. Để chỉ tạm tắt Doclint trong một tình huống chẩn đoán, có thể dùng `-Xdoclint:none`; không nên biến việc tắt kiểm tra thành chính sách build lâu dài.

**Lưu ý về phiên bản:** `-Xdoclint` là tùy chọn mở rộng (non-standard) của standard doclet và có thể thay đổi theo JDK. Chạy `javadoc --help-extra` trên đúng JDK của dự án để xác nhận nhóm và cú pháp được hỗ trợ.

## 4. Bật tất cả kiểm tra và điều chỉnh nhóm missing

Lệnh nghiêm ngặt:

```bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src com.example.api
```

`-Xdoclint:all` bật tất cả nhóm, bao gồm nhóm `missing`. Điều này hữu ích khi dự án muốn yêu cầu API được chọn có documentation đầy đủ.

Một số dự án cũ có thể đã có comment nhưng chưa mô tả đầy đủ mọi thành viên hoặc tag. Có thể bật các nhóm kiểm tra cấu trúc, HTML và reference nhưng tạm bỏ nhóm missing:

```bash
javadoc -Xdoclint:all,-missing -Werror -d build/docs -sourcepath src com.example.api
```

Cách này vẫn giữ kiểm tra lỗi cú pháp, HTML và liên kết tham chiếu, đồng thời tránh yêu cầu hoàn thiện toàn bộ comment ngay trong một lần chuyển đổi.

Nên lập kế hoạch bổ sung tài liệu còn thiếu rồi chuyển sang `-Xdoclint:all` khi dự án đã đạt baseline mong muốn. Việc bỏ nhóm missing không làm các nhóm khác biến mất.

## 5. Phân biệt error, warning và -Werror

Trong kết quả Javadoc:

- **Error:** lỗi khiến quá trình tạo tài liệu không thành công.
- **Warning:** vấn đề cần xử lý nhưng có thể không làm lệnh thất bại nếu không bật chính sách nghiêm ngặt.
- **Thông báo thông tin:** trạng thái hoặc ghi chú không nhất thiết là lỗi chất lượng.

Tùy chọn `-Werror` yêu cầu Javadoc báo lỗi nếu có warning:

```bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src com.example.api
```

Điều cần phân biệt:

- `-Xdoclint:all` quyết định những nhóm lỗi documentation nào được kiểm tra.
- `-Werror` quyết định warning có làm build thất bại hay không.
- `-Werror` không tự bật Doclint hoặc tự xác định nhóm cần kiểm tra.
- `-Werror` có thể áp dụng với warning khác do Javadoc phát ra, không chỉ warning từ Doclint.

Vì vậy, cấu hình CI thường kết hợp cả hai tùy chọn.

## 6. Ví dụ hoàn chỉnh: tạo tài liệu có kiểm tra Doclint

Cấu trúc dự án:

```text
project/
  src/
    com/
      example/
        api/
          package-info.java
          Calculator.java
  build/
```

Tệp **`src/com/example/api/package-info.java`**:

```java
/**
 * Cung cấp API tính toán số nguyên cho ứng dụng.
 *
 * <p>Package này minh họa cách tạo tài liệu API có kiểm tra Doclint.</p>
 */
package com.example.api;
```

Tệp **`src/com/example/api/Calculator.java`**:

```java
package com.example.api;

/**
 * Cung cấp các phép toán số nguyên cơ bản.
 *
 * <p>Các phương thức tiện ích trong lớp này không giữ trạng thái.</p>
 *
 * @since 1.0
 */
public final class Calculator {

    private Calculator() {
    }

    /**
     * Cộng hai số nguyên.
     *
     * @param left toán hạng thứ nhất
     * @param right toán hạng thứ hai
     * @return tổng của hai số nguyên
     * @see #subtract(int, int)
     */
    public static int add(int left, int right) {
        return left + right;
    }

    /**
     * Trừ số thứ hai khỏi số thứ nhất.
     *
     * @param left số bị trừ
     * @param right số trừ
     * @return hiệu của hai số
     */
    public static int subtract(int left, int right) {
        return left - right;
    }

    /**
     * Chia số nguyên bị chia cho số chia.
     *
     * @param dividend số nguyên bị chia
     * @param divisor số nguyên chia
     * @return thương theo quy tắc chia số nguyên của Java
     * @throws ArithmeticException nếu divisor bằng 0
     */
    public static int divide(int dividend, int divisor) {
        return dividend / divisor;
    }
}
```

### Bước 1: Tạo thư mục đầu ra

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force build\docs, build\classes | Out-Null
```

**macOS/Linux:**

```bash
mkdir -p build/docs build/classes
```

### Bước 2: Chạy Javadoc với Doclint nghiêm ngặt

Từ thư mục gốc dự án:

```bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -d build/docs -sourcepath src com.example.api
```

Lệnh thực hiện:

- Chọn package `com.example.api` từ source path `src`.
- Dùng quy tắc nền tảng Java 17 qua `--release 17`.
- Kiểm tra tất cả nhóm Doclint.
- Dùng UTF-8 để đọc mã nguồn.
- Ghi HTML vào `build/docs`.
- Dừng với trạng thái thất bại nếu còn warning.

Với ví dụ đã viết đầy đủ, Javadoc sẽ tạo tài liệu thành công nếu không có vấn đề khác trong môi trường build.

### Bước 3: Kiểm tra tài liệu được tạo

Mở tệp:

```text
build/docs/index.html
```

Kiểm tra:

- Trang package `com.example.api`.
- Trang class `Calculator`.
- Mô tả method `add`, `subtract` và `divide`.
- Tham chiếu `{@link #subtract(int, int)}`.
- Các mô tả `@param`, `@return` và `@throws`.

Doclint xác nhận nhiều vấn đề cấu trúc và tham chiếu trước khi tài liệu được tạo; vẫn cần đọc trang HTML để đánh giá nội dung có rõ ràng và đúng ý nghĩa API hay không.

### Bước 4: Biên dịch mã nguồn riêng

Javadoc không thay thế bước biên dịch. Kiểm tra mã nguồn bằng `javac`:

```bash
javac --release 17 -d build/classes -sourcepath src src/com/example/api/Calculator.java
```

Lệnh thành công không in ra nội dung nếu không có lỗi hoặc warning. Bước này kiểm tra mã Java; nó không chứng minh phần mô tả trong Javadoc đúng về mặt nghiệp vụ.

## 7. Thử nghiệm một lỗi reference có chủ đích

Một cách kiểm tra cấu hình Doclint là tạo lỗi tài liệu có thể tái hiện, xác nhận công cụ phát hiện rồi sửa lỗi.

Trong `Calculator.java`, tạm thay:

```java
@see #subtract(int, int)
```

bằng:

```java
@see #substract(int, int)
```

Tên `substract` bị viết sai; method thực tế là `subtract`.

Chạy:

```bash
javadoc --release 17 -Xdoclint:reference -Werror -encoding UTF-8 -d build/docs -sourcepath src com.example.api
```

Javadoc sẽ báo tham chiếu không được phân giải, thường với thông báo tương tự `reference not found`. Vì bật `-Werror`, warning được nâng thành lỗi và lệnh kết thúc với trạng thái thất bại.

Sửa lại:

```java
@see #subtract(int, int)
```

Chạy lại lệnh strict ở bước 2. Khi tham chiếu hợp lệ và không còn warning, tài liệu được tạo thành công.

Đây là ví dụ kiểm tra có chủ đích; không để lỗi đánh máy trong mã nguồn chính thức.

## 8. Kiểm tra HTML và accessibility

Doclint có thể kiểm tra một số vấn đề HTML và accessibility ngay trong doc comment.

Ví dụ comment chứa danh sách:

```java
/**
 * Các chế độ hỗ trợ:
 * <ul>
 *   <li>FAST: ưu tiên tốc độ.</li>
 *   <li>SAFE: ưu tiên kiểm tra đầu vào.</li>
 * </ul>
 */
```

Khi viết HTML trong Javadoc:

- Đóng các thẻ yêu cầu thẻ kết thúc.
- Lồng thẻ theo cấu trúc HTML hợp lệ.
- Dùng `{@code ...}` hoặc `{@literal ...}` khi muốn hiển thị ký tự có ý nghĩa HTML.
- Cung cấp văn bản thay thế phù hợp cho hình ảnh.
- Dùng cấu trúc bảng có tiêu đề rõ ràng nếu cần trình bày dữ liệu.
- Không đưa script hoặc nội dung HTML tùy ý vào comment nếu không có lý do và chính sách phù hợp.

Có thể chạy riêng các nhóm:

```bash
javadoc -Xdoclint:html -d build/docs -sourcepath src com.example.api
javadoc -Xdoclint:accessibility -d build/docs -sourcepath src com.example.api
```

Doclint không thay thế kiểm tra accessibility đầy đủ bằng công cụ chuyên dụng hoặc thử nghiệm với trình đọc màn hình. Nó chỉ phát hiện một số vấn đề thuộc phạm vi kiểm tra của Javadoc.

## 9. Kiểm tra tài liệu còn thiếu bằng nhóm missing

Nhóm `missing` giúp phát hiện API chưa được mô tả đầy đủ theo quy tắc Doclint.

Ví dụ, nếu một method public có tham số nhưng doc comment không có `@param`, hoặc một thành viên cần tài liệu nhưng chưa có comment, nhóm missing có thể đưa ra warning tương ứng.

Chạy:

```bash
javadoc -Xdoclint:missing -d build/docs -sourcepath src com.example.api
```

Để kiểm tra tất cả nhóm cùng yêu cầu không còn warning:

```bash
javadoc -Xdoclint:all -Werror -d build/docs -sourcepath src com.example.api
```

Khi dùng `-private`, phạm vi thành viên được đưa vào tài liệu rộng hơn. Nếu dự án bật kiểm tra missing, số lượng thành viên cần có comment cũng có thể tăng. Chọn mức hiển thị phù hợp với mục tiêu tài liệu:

- API công khai: thường dùng mức public/protected.
- Tài liệu nội bộ: có thể dùng `-private` khi muốn ghi lại cả chi tiết nội bộ.
- Không dùng `-private` chỉ để làm mất warning nếu điều đó khiến tài liệu công bố thông tin triển khai không mong muốn.

## 10. Chọn nhóm kiểm tra có chủ đích

Có thể kết hợp nhiều nhóm hoặc tạm loại trừ một nhóm:

```bash
javadoc -Xdoclint:all,-missing -Werror -d build/docs -sourcepath src com.example.api
```

Một số cách dùng:

| Mục tiêu | Tùy chọn |
| --- | --- |
| Bật tất cả nhóm | `-Xdoclint:all` |
| Tắt Doclint | `-Xdoclint:none` |
| Chỉ kiểm tra HTML | `-Xdoclint:html` |
| Chỉ kiểm tra tham chiếu | `-Xdoclint:reference` |
| Chỉ kiểm tra cú pháp | `-Xdoclint:syntax` |
| Chỉ kiểm tra accessibility | `-Xdoclint:accessibility` |
| Kiểm tra tài liệu còn thiếu | `-Xdoclint:missing` |
| Bật tất cả, trừ missing | `-Xdoclint:all,-missing` |

Nếu một nhóm gây warning do nội dung legacy, hãy ghi nhận rõ phạm vi và kế hoạch sửa. Tránh dùng `-Xdoclint:none` như một cách xử lý lâu dài vì nó loại bỏ toàn bộ kiểm tra Doclint.

## 11. Tích hợp Doclint vào CI

Một pipeline tài liệu có thể chạy các bước sau:

1. Build mã nguồn và dependency.
2. Tạo Javadoc với `-Xdoclint:all -Werror`.
3. Nếu Javadoc thất bại, đánh dấu job CI thất bại.
4. Nếu thành công, lưu thư mục HTML làm build artifact.
5. Kiểm tra các trang chính và liên kết quan trọng trước khi phát hành.

Lệnh CI cơ bản:

```bash
javadoc --release 17 -Xdoclint:all -Werror -encoding UTF-8 -d build/docs -sourcepath src -subpackages com.example
```

Dùng `-subpackages` khi muốn quét cả cây package. Nếu chỉ muốn công bố một số package, truyền tên package cụ thể để tránh đưa mã nội bộ vào tài liệu.

Trong Maven hoặc Gradle, cấu hình cùng các compiler/Javadoc arguments trong tác vụ tạo tài liệu. Hãy giữ phiên bản plugin và JDK nhất quán giữa máy phát triển và CI, đồng thời kiểm tra log để biết warning đến từ Javadoc, plugin hay một bước khác.

## 12. Doclint không kiểm tra những gì?

Doclint hữu ích nhưng có giới hạn. Nó không tự động xác nhận:

- Nội dung mô tả thuật toán có đúng với hành vi thực tế hay không.
- Ví dụ Java trong comment có biên dịch và chạy thành công hay không.
- Ví dụ có cho ra kết quả đúng theo yêu cầu nghiệp vụ hay không.
- Mọi URL bên ngoài có còn hoạt động hay không.
- Giao diện HTML hiển thị tốt trên mọi trình duyệt và kích thước màn hình hay không.
- Tài liệu có dễ hiểu, đầy đủ ngữ cảnh và phù hợp với người đọc hay không.
- API có an toàn, hiệu quả hoặc thread-safe đúng như comment tuyên bố hay không.

Để kiểm tra toàn diện, kết hợp:

- Doclint cho cấu trúc comment, tag, HTML và reference.
- `javac` hoặc build tool cho khả năng biên dịch mã nguồn.
- Unit test cho hành vi API.
- Kiểm tra HTML/link và accessibility bằng công cụ chuyên dụng.
- Review nội dung tài liệu trong code review.

## 13. Lỗi thường gặp khi kiểm thử documentation

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Javadoc báo `reference not found` | `{@link}`, `@see` hoặc tham chiếu method sai tên/chữ ký | Kiểm tra tên class, method, tham số và import |
| Warning về HTML | Thẻ sai cú pháp, thiếu đóng hoặc lồng không hợp lệ | Sửa cấu trúc HTML trong doc comment |
| Warning accessibility | Nội dung HTML thiếu thông tin hỗ trợ khả năng truy cập | Bổ sung alt text và cấu trúc phù hợp |
| Warning missing | Thiếu doc comment hoặc tag được kiểm tra | Bổ sung mô tả và tag tương ứng hoặc xác định chính sách missing |
| Build thất bại sau khi bật `-Werror` | Có warning từ Javadoc hoặc Doclint | Đọc warning đầu tiên, sửa nguyên nhân và chạy lại |
| Chỉ một số package có warning | Phạm vi source hoặc mức hiển thị khác nhau | Kiểm tra package selection, source path và visibility |
| Máy local chạy được nhưng CI thất bại | Khác JDK, encoding, dependency hoặc cấu hình Doclint | Đồng bộ JDK, plugin, source và arguments |
| Doclint không phát hiện nội dung mô tả sai | Đây là lỗi ngữ nghĩa, nằm ngoài phạm vi Doclint | Bổ sung test, review API và kiểm tra ví dụ |
| Tài liệu không tạo được dù comment đúng | Javadoc không phân giải được source hoặc dependency | Kiểm tra `-sourcepath`, classpath, module path và package selection |

## 14. Quy trình kiểm thử documentation đề xuất

Một quy trình có thể lặp lại cho mỗi lần phát hành:

1. Xác định package hoặc module cần tạo tài liệu.
2. Chọn source và dependency bằng `-sourcepath`, `-classpath` hoặc module path phù hợp.
3. Chạy `javadoc -Xdoclint:all` để kiểm tra mọi nhóm.
4. Bật `-Werror` trong CI để warning làm build thất bại.
5. Sửa các lỗi HTML, syntax, reference và accessibility.
6. Bổ sung comment và tag còn thiếu nếu dự án yêu cầu nhóm missing.
7. Chạy `javac` hoặc build tool để kiểm tra mã nguồn độc lập.
8. Chạy unit test cho hành vi được mô tả.
9. Mở các trang HTML được tạo và kiểm tra nội dung, điều hướng, encoding.
10. Lưu Javadoc cùng phiên bản artifact được phát hành.

Khi chuyển đổi một codebase cũ, có thể bắt đầu bằng `-Xdoclint:all,-missing`, xử lý các lỗi cấu trúc trước, sau đó bổ sung comment và bật `-Xdoclint:all -Werror`.

## 15. Ghi nhớ

- Doclint là bộ kiểm tra documentation comments được tích hợp trong Javadoc.
- Các nhóm chính gồm `accessibility`, `html`, `missing`, `reference` và `syntax`.
- Dùng `-Xdoclint:all` để bật tất cả nhóm kiểm tra.
- Dùng `-Xdoclint:none` để tắt Doclint; chỉ nên dùng cho chẩn đoán có chủ đích.
- Dùng `-Xdoclint:all,-missing` khi cần kiểm tra cấu trúc nhưng tạm hoãn yêu cầu tài liệu đầy đủ.
- Dùng `-Werror` để làm cho warning khiến bước tạo tài liệu thất bại.
- Doclint kiểm tra cấu trúc và tham chiếu; nó không chạy ví dụ hoặc xác minh tính đúng đắn nghiệp vụ.
- Kết hợp Doclint, biên dịch, unit test và review HTML để kiểm soát chất lượng tài liệu.
- Dùng `javadoc --help-extra` để xác nhận tùy chọn mở rộng trên JDK đang sử dụng.

Đưa Doclint vào quy trình build giúp lỗi documentation được phát hiện sớm, trước khi tài liệu API đến tay người dùng thư viện hoặc được phát hành cùng sản phẩm.
