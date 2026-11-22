# Thay đổi quy ước mà không trộn nhiễu định dạng với sửa hành vi

Một pull request sửa một điều kiện tính phí giao hàng chỉ cần thay dấu **>** thành **>=**. Nhưng nếu người sửa đồng thời chạy formatter trên toàn bộ module, bản diff có thể chứa hàng nghìn dòng đổi dấu cách, xuống dòng và cách sắp xếp mã. Người review phải tìm một thay đổi hành vi quan trọng giữa rất nhiều thay đổi trình bày. Nguy cơ bỏ sót lỗi vì thế tăng lên, dù mã sau khi format trông đồng nhất hơn.

Trong module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Ở chương **Quy ước và nhất quán**, vấn đề không chỉ là chọn kiểu thụt dòng hay cách đặt tên. Điều quan trọng còn là **thay đổi quy ước đúng cách** để mã nhất quán hơn mà không làm mờ thay đổi chức năng, hợp đồng hoặc tác dụng phụ.

Bài này giúp bạn phân biệt **format-only change**, **refactor giữ hành vi**, **thay đổi hợp đồng** và **sửa hành vi**; tổ chức commit/PR; sử dụng formatter, kiểm thử và review như những lớp bảo vệ bổ sung, không nhầm công cụ định dạng với bằng chứng mã vẫn đúng.

## 1. Vì sao tính nhất quán có giá trị?

Một codebase nhất quán giúp người đọc dự đoán:

- Tên lớp, phương thức và biến thường nói lên điều gì.
- Điều kiện, ngoại lệ, null và kết quả trả về được biểu diễn ra sao.
- Các file, package, module và test có cấu trúc thế nào.
- Người sửa nên tìm quy tắc nghiệp vụ ở đâu.
- Lệnh nào áp dụng định dạng chuẩn và cách CI kiểm tra nó.

Nhờ đó, người bảo trì tập trung vào **hành vi khác biệt** thay vì liên tục giải mã phong cách của từng tác giả. Quy ước có thể bao gồm thụt dòng, dấu ngoặc, thứ tự import, cách đặt tên, cách tổ chức class, thông báo lỗi hoặc nguyên tắc viết test.

Tuy nhiên, các loại quy ước có **mức rủi ro thay đổi khác nhau**. Đổi độ rộng thụt dòng không giống đổi tên một phương thức public. Càng liên quan đến hợp đồng, hành vi runtime hoặc cơ chế framework, càng không nên gom vào một thay đổi “format code”.

**Mục tiêu của một đợt chuẩn hóa** là giảm chi phí đọc và sửa mã về sau, **không tạo chi phí review quá lớn ngay trong đợt chuẩn hóa**.

## 2. Bốn loại thay đổi cần tách bạch

| Loại thay đổi | Mục tiêu | Ví dụ | Có thể ảnh hưởng hành vi/hợp đồng? |
| --- | --- | --- | --- |
| **Định dạng thuần túy (format-only)** | Chỉnh cách trình bày mà giữ nguyên token và ý nghĩa chương trình. | Thụt dòng, xuống dòng, khoảng trắng ngoài literal. | Dự kiến không; vẫn phải xác minh các trường hợp nhạy cảm. |
| **Refactor giữ hành vi** | Đổi cấu trúc để dễ hiểu hoặc dễ sửa mà vẫn giữ kết quả quan sát được theo hợp đồng. | Trích xuất phương thức, chuyển một nhánh vào guard clause, tách trách nhiệm. | Có thể nếu thực hiện sai; cần test tương đương. |
| **Thay đổi hợp đồng** | Đổi điều bên ngoài được phép dựa vào. | Đổi tên public method, mã lỗi, kiểu response, cấu hình mặc định. | Có; cần xem tương thích và migration. |
| **Sửa/thêm hành vi** | Đổi kết quả chương trình theo yêu cầu. | Chuyển điều kiện phí miễn ship từ > thành >=. | Có chủ đích; phải có test bảo vệ hành vi mới. |

Từ **format-only** nên được dùng nghiêm ngặt: chỉ thay đổi biểu diễn bề mặt của mã khi **ý nghĩa và cấu trúc token không đổi**. Việc thêm dấu ngoặc nhọn, đổi import, trích xuất biến hay dùng toán tử khác không mặc nhiên là thay đổi định dạng, dù một công cụ tự động có thể hỗ trợ thao tác đó.

### Những việc thường bị nhầm là format-only

- **Đổi tên class hoặc method:** có thể ảnh hưởng API, reflection, serialization, script hoặc client bên ngoài.
- **Sắp xếp/sửa import:** chỉ sắp thứ tự import tường minh thường không thay đổi chương trình Java, nhưng thêm/bớt static import, đổi wildcard import hoặc xử lý tên trùng có thể ảnh hưởng việc phân giải tên.
- **Chuyển vòng lặp sang Stream:** là refactor; có thể thay đổi thứ tự, cách xử lý lỗi, lazy evaluation hoặc tác dụng phụ.
- **Đổi if/else thành biểu thức boolean:** có thể thay đổi thứ tự đánh giá, short-circuit và ngoại lệ.
- **Chuyển kiểu tường minh sang var:** có thể thay đổi kiểu suy luận ở một số cấu trúc và ảnh hưởng lựa chọn lời gọi tiếp theo.
- **Thay thông báo log hoặc exception:** có thể ảnh hưởng công cụ theo dõi, test và người dùng dù kết quả tính toán giữ nguyên.
- **Đổi định dạng JSON:** whitespace của JSON object thường không ảnh hưởng ý nghĩa dữ liệu, nhưng có thể ảnh hưởng chữ ký, so sánh byte hoặc client phụ thuộc biểu diễn.

Đừng dùng nhãn “dọn mã” để che một thay đổi chức năng.

## 3. Ví dụ xuyên suốt: chỉ một dấu so sánh cũng quan trọng

Giả sử chính sách nghiệp vụ đã được xác nhận:

1. Tổng tiền hàng phải không âm.
2. Đơn từ **500.000 VND trở lên** được miễn phí giao hàng tiêu chuẩn.
3. Đơn dưới ngưỡng trả phí tiêu chuẩn **30.000 VND**.
4. Giao nhanh cộng **20.000 VND**, kể cả khi phí tiêu chuẩn bằng 0.

Implementation ban đầu có một lỗi nhỏ: điều kiện dùng **>** thay vì **>=**. Để thấy rõ sự khác biệt giữa định dạng và hành vi, chúng ta cố ý **chưa sửa lỗi** ở bước chuẩn hóa phong cách.

### Bản trước khi định dạng

~~~java
public static long calculate(long subtotalVnd,boolean express){
    if(subtotalVnd<0){throw new IllegalArgumentException("negative");}
    long standardFee=subtotalVnd>500_000L?0L:30_000L;
    return express?standardFee+20_000L:standardFee;
}
~~~

### Bản sau khi chỉ thay định dạng

~~~java
public static long calculate(long subtotalVnd, boolean express) {
    if (subtotalVnd < 0) {
        throw new IllegalArgumentException("negative");
    }

    long standardFee = subtotalVnd > 500_000L
            ? 0L
            : 30_000L;
    return express ? standardFee + 20_000L : standardFee;
}
~~~

Bản thứ hai có dấu cách và xuống dòng nhất quán hơn, nhưng **vẫn giữ dấu >**, cùng tên, giá trị, biểu thức và thứ tự thao tác. Vì thế, nếu không có ràng buộc khác từ môi trường, hai bản này dự kiến có cùng hành vi, **bao gồm cả lỗi tại đúng ngưỡng**.

Điều đó là chủ đích của một thay đổi format-only: không âm thầm sửa lỗi trong lúc đổi phong cách. **Lỗi sẽ được sửa ở một thay đổi riêng và có bằng chứng kiểm thử.**

### Sửa hành vi ở bước tiếp theo

Trong một commit hoặc pull request chức năng riêng, thay đúng điều kiện:

~~~diff
-    long standardFee = subtotalVnd > 500_000L
+    long standardFee = subtotalVnd >= 500_000L
             ? 0L
             : 30_000L;
~~~

Diff này giúp người review thấy ngay quyết định nghiệp vụ đã đổi: **đơn đúng 500.000 VND được miễn phí tiêu chuẩn**. Không cần dò trong hàng loạt dòng có cách thụt lề mới.

Khi có nhiều thay đổi độc lập, thứ tự phù hợp thường là **format-only → thay đổi hành vi**, hoặc ngược lại nếu sửa lỗi gấp; điều quan trọng là **phân tách ranh giới có thể review** và xác nhận hành vi ở từng bước.

## 4. Vì sao trộn formatting với sửa hành vi gây rủi ro?

Một thay đổi lẫn hai mục tiêu tạo ra nhiều vấn đề:

| Rủi ro | Biểu hiện | Hậu quả |
| --- | --- | --- |
| **Nhiễu diff** | Hàng trăm dòng chỉ đổi dấu cách bao quanh vài dòng có ý nghĩa. | Reviewer bỏ sót điều kiện hoặc thay đổi giá trị. |
| **Khó xác định nguyên nhân** | Một commit vừa thay thuật toán vừa dọn cả file. | Khó biết phần nào gây lỗi hồi quy. |
| **Khó cherry-pick và rollback** | Bản vá chức năng đi kèm định dạng lớn. | Tăng xung đột khi đưa sang nhánh bảo trì. |
| **Khó so sánh trước/sau** | File đổi vị trí và cách trình bày cùng lúc. | Công cụ diff khó phát hiện chuyển mã thực sự. |
| **Blame mất tín hiệu** | Mỗi dòng đều mang commit format mới. | Khó tìm người và lý do sửa logic trước đó. |
| **Test khó chứng minh ranh giới** | CI chỉ chạy sau khi tất cả thay đổi đã gộp. | Không biết format đã an toàn trước khi sửa hành vi chưa. |
| **Review quá tải** | Một PR lớn nhiều mục tiêu. | Đánh giá bảo mật, hợp đồng và nghiệp vụ kém tập trung. |

**Đây không phải lập luận chống formatter.** Formatter rất hữu ích. Rủi ro đến từ việc **không kiểm soát thời điểm, phạm vi và loại thay đổi** mà formatter tạo ra.

## 5. Format-only thật sự có giữ nguyên mọi thứ không?

Đối với Java thông thường, việc đổi khoảng trắng **giữa các token** mà không đổi nội dung literal, comment có ý nghĩa hoặc cấu trúc cú pháp thường không làm đổi kết quả tính toán. Nhưng từ “thường” quan trọng: **không nên coi mọi thay đổi whitespace đều vô hại**.

Những vị trí cần chú ý:

- **String literal và text block:** khoảng trắng **bên trong giá trị chuỗi** có thể là dữ liệu. Java text block có quy tắc về thụt lề và khoảng trắng; thay đổi chúng có thể làm khác giá trị kết quả.
- **Comment và dấu xuống dòng:** một dấu xuống dòng có thể quyết định phần nào của mã nằm trong line comment. Công cụ format hợp lệ phải giữ cấu trúc cú pháp.
- **File cấu hình nhạy với whitespace:** YAML, Makefile, Python và một số ngôn ngữ dùng whitespace mang ý nghĩa cú pháp; không áp dụng giả định của Java cho mọi file.
- **File dùng để ký số hoặc so sánh byte:** đổi line ending, encoding hoặc khoảng trắng có thể thay đổi hash/chữ ký dù logic ứng dụng không đổi.
- **Generated code, file vendor, migration:** nội dung có thể được công cụ khác quản lý hoặc ràng buộc theo phiên bản; không tự format tùy tiện.
- **Javadoc, tài liệu và ví dụ:** đổi khoảng trắng chỉ để trình bày là một việc; đổi mô tả hợp đồng hoặc giá trị trong ví dụ là thay đổi nội dung.

Ví dụ **hai chuỗi khác nhau về dữ liệu**:

~~~java
String expectedA = "A B";
String expectedB = "AB";

assert !expectedA.equals(expectedB);
~~~

Khoảng trắng ở đây là một phần giá trị. Nếu bỏ khoảng trắng trong literal, đó **không phải thay đổi định dạng thuần túy**.

**Nguyên tắc kiểm chứng:** không chỉ hỏi “diff trông có giống format không?”, mà hỏi “có token, literal, annotation, hợp đồng hoặc tác dụng phụ nào đã thay đổi không?”.

## 6. Quy ước nên có nguồn chuẩn duy nhất

Một dự án dễ rơi vào tình trạng người A dùng formatter của IDE, người B dùng cấu hình khác, CI lại áp dụng quy tắc thứ ba. Kết quả là mỗi lần mở file lại phát sinh diff trình bày không cần thiết.

Một cách thống nhất phù hợp:

1. **Chọn bộ quy tắc tối thiểu**, ưu tiên khả năng tự động hóa và sự quen thuộc của nhóm.
2. **Lưu cấu hình cạnh mã** để mọi người dùng cùng phiên bản/thiết lập có thể tái lập.
3. **Ghi rõ cách chạy formatter và linter**, cũng như cách CI kiểm tra.
4. **Phân biệt formatter và quy tắc khác**: formatter làm trình bày, linter/checker có thể kiểm tra lỗi tiềm ẩn, quy tắc tổ chức mã cần review.
5. **Có người chịu trách nhiệm thay quy ước** để thay đổi không diễn ra ngẫu nhiên theo sở thích cá nhân.

Ví dụ một phần file cấu hình **.editorconfig**:

~~~ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true

[*.java]
indent_style = space
indent_size = 4
~~~

EditorConfig giúp các công cụ hỗ trợ thống nhất những thuộc tính cơ bản của file. Nó **không tự định nghĩa đầy đủ** cách xuống dòng method chain, import, annotation hoặc mọi lựa chọn định dạng Java. Muốn bảo đảm những chi tiết đó cần một formatter và cấu hình tương ứng, được quản lý cùng codebase.

Không nên tạo cấu hình chỉ nhằm ép một nhóm style mới mà thiếu đánh giá chi phí chuyển đổi, đặc biệt với repository lớn hoặc có nhiều nhánh bảo trì.

## 7. Thứ tự thực hiện một đợt thay đổi quy ước

Một kế hoạch giảm nhiễu có thể gồm các pha:

~~~mermaid
flowchart TD
    A["Xác định quy ước muốn đổi"] --> B["Đánh giá phạm vi và rủi ro"]
    B --> C["Chốt cấu hình và công cụ"]
    C --> D["Tạo thay đổi format-only cô lập"]
    D --> E["Kiểm tra raw diff, build và test"]
    E --> F{"Có thay đổi ngoài phạm vi định dạng?"}
    F -- "Có" --> G["Tách hoặc sửa các thay đổi không phù hợp"]
    G --> E
    F -- "Không" --> H["Review và tích hợp format-only"]
    H --> I["Thực hiện sửa hành vi/refactor riêng"]
    I --> J["Test hợp đồng và review nghiệp vụ"]
~~~

### Pha 1 — Xác định thay đổi cần đạt

Ví dụ: “Toàn bộ Java source trong module Checkout dùng bốn dấu cách để thụt lề và formatter phiên bản đã chốt”.

Không viết mục tiêu mơ hồ như “dọn lại mọi thứ cho sạch”. Một thay đổi quy ước tốt cần có **phạm vi và tiêu chí hoàn tất kiểm tra được**.

### Pha 2 — Chốt phạm vi

Cần xác định:

- Những thư mục/file nguồn nào thuộc đợt chuẩn hóa?
- Generated code, vendored source, migration hoặc ví dụ trong docs có bị loại trừ không?
- Có nhiều ngôn ngữ với quy tắc whitespace khác nhau không?
- Nhánh bảo trì và các PR đang mở sẽ chịu ảnh hưởng ra sao?
- Codebase có đang có những thay đổi chức năng chưa merge, dễ gây xung đột không?

Không nhất thiết format toàn repository ngay. Có thể giới hạn theo module hoặc theo file mới sửa nếu chi phí đồng bộ quá lớn.

### Pha 3 — Ghi lại baseline

Trước thay đổi format-only, ghi nhận **trạng thái test/build** ở phiên bản gốc. Nếu baseline đã có lỗi, cần biết lỗi nào có trước, thay vì quy mọi thất bại sau đó cho formatter.

Có thể dùng các lệnh Git và build phù hợp dự án; đây là ví dụ tham khảo, **không phải báo cáo rằng các lệnh đã được chạy**:

~~~bash
git status --short
git diff --check

# Dùng lệnh build/test mà dự án thực sự định nghĩa:
./gradlew test
~~~

Nếu dự án không có Gradle hoặc chưa cấu hình test, không dùng nguyên lệnh minh họa như một cam kết chạy được. Điểm cốt lõi là có **bằng chứng baseline và cơ chế so sánh**.

### Pha 4 — Chỉ thay định dạng

Áp dụng công cụ đã chốt lên **phạm vi chọn trước**. Trong commit này không đồng thời sửa điều kiện, đổi API, thêm quy tắc nghiệp vụ hoặc “tiện tay” xóa code.

Chú ý formatter hoặc tính năng **Organize Imports** có thể thực hiện nhiều hơn việc chỉnh khoảng trắng. Cần xem cấu hình, bản diff và những thay đổi import trước khi gọi toàn bộ kết quả là format-only.

### Pha 5 — Review và xác minh

Kiểm tra raw diff, chạy test/build tương ứng và xác nhận không có nội dung ngoài mục tiêu. Một bước so sánh bỏ qua whitespace có thể hỗ trợ rà soát nhưng **không thay thế đọc diff nguyên bản**.

### Pha 6 — Sửa hành vi hoặc refactor riêng

Sau khi đợt chuẩn hóa đã được tích hợp hoặc được giữ thành một commit riêng, tiếp tục thay đổi chức năng với test hành vi và review theo yêu cầu. Với lỗi phí giao hàng ở phần 3, commit riêng đổi **>** thành **>=**.

## 8. Cách đọc diff để tìm nhiễu và thay đổi thực sự

Các lệnh Git dưới đây minh họa chức năng hỗ trợ review:

~~~bash
# Xem chính xác mọi thay đổi của working tree:
git diff

# Kiểm tra lỗi whitespace được Git nhận diện:
git diff --check

# Hỗ trợ nhận ra khác biệt khi bỏ qua một số thay đổi whitespace:
git diff --ignore-all-space

# Xem khác biệt theo từ, hữu ích ở một số trường hợp:
git diff --word-diff
~~~

**Cảnh báo quan trọng:** kết quả của **git diff --ignore-all-space** có thể che mất một thay đổi whitespace có ý nghĩa, chẳng hạn thay đổi khoảng trắng trong string literal hoặc file nhạy với khoảng trắng. Nó **không chứng minh mã tương đương**. Luôn xem **raw diff**, nhất là ở literal, comment, text block, file cấu hình và các dòng đổi giá trị.

**git diff --check** giúp phát hiện một số lỗi khoảng trắng; nó không biên dịch, chạy kiểm thử hoặc chứng minh hành vi đúng.

### Review theo thứ tự có chủ đích

1. Xem **danh sách file đổi**: có file ngoài phạm vi không?
2. Xem **raw diff**: có token, literal hoặc đường gọi thay đổi không?
3. Dùng công cụ hiển thị diff khác nhau **để hỗ trợ**, không dùng chế độ bỏ qua whitespace làm bằng chứng duy nhất.
4. Xem **import, annotation, text block, resource, generated files** riêng nếu formatter chạm vào.
5. Kiểm tra build/test và cách chạy formatter đã được ghi lại.
6. Ghi rõ phần nào chỉ là trình bày, phần nào cần thay đổi chức năng ở PR kế tiếp.

Nếu không thể review một thay đổi định dạng quá lớn với mức tin cậy hợp lý, hãy **chia phạm vi** thay vì vội merge chỉ vì công cụ tự động tạo diff.

## 9. Commit, pull request và cách đặt ranh giới review

Tùy độ lớn và lịch triển khai, có thể chọn một trong các cách sau:

| Cách tổ chức | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| **PR format-only riêng** | Chuẩn hóa rộng hoặc nhiều file. | Review mục tiêu định dạng, không trộn thay đổi chức năng. |
| **Hai commit riêng trong một PR** | Thay đổi nhỏ, không thể tách PR do phụ thuộc hoặc lịch triển khai. | Mỗi commit nên có mục đích rõ; reviewer xem từng commit và diff tổng. |
| **Chỉ format file/dòng vừa sửa** | Repository lớn, nhiều nhánh và chưa có kế hoạch chuẩn hóa toàn bộ. | Cần nhất quán với quy ước đang áp dụng để tránh drift. |
| **Format toàn module theo nhiều đợt** | Khó chịu nổi diff rất lớn cùng lúc. | Chọn ranh giới độc lập, phối hợp các PR đang mở. |

Một cặp commit có thể mang tên:

~~~text
style(checkout): apply agreed Java formatting
fix(checkout): include threshold in free standard shipping
~~~

Tên commit chỉ là ví dụ. Phần quan trọng là **một commit cho thay đổi trình bày, một commit cho quyết định nghiệp vụ**.

### Khi nào một PR hai commit chưa đủ?

Nếu PR format chạm hàng nghìn dòng, sau đó commit sửa hành vi chạm lại đúng file, bản diff tổng vẫn lớn. Reviewer phải chủ động xem riêng commit chức năng. Với thay đổi rủi ro cao, ưu tiên **PR độc lập**, merge format-only trước rồi đưa chức năng lên base đã chuẩn hóa.

Trong trường hợp bug bảo mật hoặc sự cố sản xuất cần sửa gấp, không nhất thiết trì hoãn sửa lỗi để format trước: **ưu tiên bản vá hành vi nhỏ, có test**, rồi lên kế hoạch chuẩn hóa sau.

## 10. Ví dụ bảo vệ thay đổi hành vi bằng JUnit 5

Sau khi chuẩn hóa định dạng riêng, implementation đã sửa điều kiện có thể là:

~~~java
public final class ShippingFeePolicy {
    private static final long FREE_THRESHOLD = 500_000L;
    private static final long STANDARD_FEE = 30_000L;
    private static final long EXPRESS_SURCHARGE = 20_000L;

    private ShippingFeePolicy() {
    }

    public static long calculate(long subtotalVnd, boolean express) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException("negative");
        }

        long standardFee = subtotalVnd >= FREE_THRESHOLD
                ? 0L
                : STANDARD_FEE;
        return express ? standardFee + EXPRESS_SURCHARGE : standardFee;
    }
}
~~~

Các ca JUnit 5 cần xác nhận ranh giới đúng:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    @Test
    void belowThresholdPaysStandardFee() {
        assertEquals(30_000L,
                ShippingFeePolicy.calculate(499_999L, false));
    }

    @Test
    void atThresholdGetsFreeStandardShipping() {
        assertEquals(0L,
                ShippingFeePolicy.calculate(500_000L, false));
    }

    @Test
    void expressStillAddsSurchargeAtThreshold() {
        assertEquals(20_000L,
                ShippingFeePolicy.calculate(500_000L, true));
    }

    @Test
    void expressBelowThresholdPaysBothComponents() {
        assertEquals(50_000L,
                ShippingFeePolicy.calculate(499_999L, true));
    }

    @Test
    void negativeSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFeePolicy.calculate(-1L, false));
    }
}
~~~

Tại bước **format-only**, các test đã có ở baseline phải tiếp tục cho cùng kết quả. Riêng test **atThresholdGetsFreeStandardShipping** được bổ sung để chứng minh **lỗi hành vi tại đúng ngưỡng**: nó sẽ thất bại với toán tử **>** và thành công sau khi sửa thành **>=**.

Không cần cố làm test mới này xanh trong commit chỉ định dạng bằng cách sửa luôn toán tử. Hãy đưa test và bản sửa nghiệp vụ vào thay đổi hành vi riêng, hoặc ghi lại rõ quá trình test đỏ → sửa mã → test xanh trong PR sửa lỗi.

## 11. Test xanh vẫn chưa đủ để gọi thay đổi là an toàn

Kiểm thử là bằng chứng có giá trị, nhưng test chỉ nhận biết hành vi đã được assert hoặc quan sát. Một formatter cấu hình sai có thể đổi dữ liệu trong text block mà không làm test hiện tại thất bại nếu chưa có test cho nội dung ấy.

Những lớp bảo vệ nên kết hợp:

| Bằng chứng | Giúp phát hiện điều gì? | Không chứng minh được điều gì? |
| --- | --- | --- |
| **Raw diff chỉ có trình bày** | Có token, giá trị hoặc tài liệu nào đổi bất ngờ không? | Không phải chứng minh hình thức đầy đủ cho mọi trường hợp. |
| **Build/compile thành công** | Mã còn hợp lệ và các tham chiếu biên dịch được. | Kết quả nghiệp vụ và tác dụng phụ vẫn đúng. |
| **Unit tests** | Các trường hợp được kiểm tra có giữ nguyên kết quả không? | Các hành vi chưa có assertion. |
| **Integration/contract tests** | Tương tác, serialization, DB, framework và hợp đồng ở ranh giới. | Mọi tình huống tải, bảo mật và điều kiện đồng thời. |
| **Formatter check trong CI** | Tính tái lập của quy ước trình bày. | Ý nghĩa nghiệp vụ hay quyền truy cập. |
| **Review của người sở hữu code** | Bối cảnh, ảnh hưởng ngoài phạm vi test và ngoại lệ cần thiết. | Không thể thay thế toàn bộ việc kiểm chứng. |

Độ mạnh của bằng chứng phải tương xứng với rủi ro. Chuẩn hóa khoảng trắng trong một helper đơn giản ít nguy hiểm hơn thay đổi import, annotation hoặc cấu trúc tại ranh giới transaction, security và serialization.

## 12. Quy ước đặt tên không phải chỉ là định dạng

Một đợt chuẩn hóa có thể muốn đổi:

- getFee thành calculateShippingFee;
- flag thành isEligible;
- DTO suffix hoặc tên package;
- tên enum, mã lỗi, tên trường JSON;
- nhãn metrics và cấu trúc logging.

Những thay đổi này liên quan đến **khả năng hiểu và tính nhất quán**, nhưng không phải format-only. Đặc biệt với Java, đổi một tên public có thể ảnh hưởng:

1. **Source compatibility:** mã ở module khác không còn biên dịch nếu gọi tên cũ.
2. **Binary compatibility:** bytecode đã biên dịch có thể không tìm được phương thức cũ.
3. **Reflection/framework:** tên lớp, phương thức hoặc trường có thể được tra cứu bằng chuỗi.
4. **Serialization:** tên property và schema có thể là hợp đồng với client.
5. **Monitoring:** công cụ quan sát có thể phân nhóm theo tên metric hoặc log field.
6. **Documentation:** ví dụ, Javadoc và hướng dẫn tích hợp có thể cần cập nhật.

Với refactor tên nội bộ, IDE rename có thể hữu ích, nhưng vẫn cần xem phạm vi và các tham chiếu động. Với tên public, có thể cần lớp tương thích hoặc kế hoạch chuyển đổi thay vì đổi hàng loạt.

**Đừng gắn nhãn format-only cho một PR đổi tên API chỉ vì logic tính toán giữ nguyên.**

## 13. Tính nhất quán không có nghĩa áp dụng một quy ước cho mọi ngữ cảnh

Một codebase có thể bao gồm Java, SQL, JSON, YAML, Markdown, shell script và source được sinh. Mỗi loại có quy tắc cú pháp và công cụ khác nhau.

Ví dụ:

| Phạm vi | Quy ước có thể phù hợp | Nguy cơ khi áp dụng máy móc |
| --- | --- | --- |
| **Java source** | Formatter thống nhất về khoảng trắng, xuống dòng và import theo cấu hình. | Công cụ import cleanup hoặc refactor đi kèm đổi ngữ nghĩa. |
| **SQL migration** | Cách thụt dòng, viết tên cột và chú thích dễ hiểu. | Không được vô tình đổi thứ tự statement, literal hay migration đã chạy. |
| **YAML** | Thụt dòng nhất quán và quote rõ khi cần. | Sai indentation làm đổi cấu trúc dữ liệu. |
| **JSON** | Định dạng dễ đọc, giữ schema. | Đổi byte có thể ảnh hưởng chữ ký hoặc snapshot. |
| **Markdown/Javadoc** | Heading, ví dụ, bảng và thuật ngữ thống nhất. | Câu diễn giải hợp đồng có thể đổi nghĩa. |
| **Generated code** | Định dạng do generator sở hữu. | Sửa tay bị ghi đè ở lần sinh tiếp theo. |

Nên xác định rõ **phạm vi quản lý bởi formatter** và **những ngoại lệ có lý do**, thay vì cố ép mọi file theo một công cụ.

## 14. Dùng formatter khi làm việc trên nhánh nhiều thay đổi

Khi codebase có nhiều người cùng phát triển, format hàng loạt có thể làm tăng xung đột merge. Một số nguyên tắc phối hợp:

- **Thông báo phạm vi và thời điểm** format-only để các nhánh đang mở biết cách rebase hoặc đồng bộ.
- **Ưu tiên thay đổi định dạng ở giai đoạn ít biến động** nếu đang có nhiều PR chạm cùng file.
- **Không trộn tính năng đang dở dang** vào commit format-only.
- **Sau khi quy ước mới được merge**, chỉnh formatter của IDE và CI để tránh diff đảo qua lại.
- **Với nhánh bảo trì**, cân nhắc giữ phong cách cũ nếu việc mang commit format sang gây xung đột không cần thiết.
- **Nếu formatter thay phiên bản**, xác định và review đó như một đợt migration riêng, không chỉ nâng plugin trong PR sửa bug.

Nên tránh tình trạng hai nhóm dùng hai version formatter làm cùng một file đổi qua đổi lại ở mỗi PR. **Khả năng tái lập** là một phần giá trị của quy ước.

## 15. Không nên sửa tay từng dòng để “đạt chuẩn” nếu có công cụ

Đối với quy tắc trình bày có thể tự động hóa, format thủ công trên nhiều tệp thường dẫn đến thiếu nhất quán. Một formatter được cấu hình và kiểm tra trong CI giúp giảm tranh luận và sửa lỗi lặp.

Tuy nhiên, không phải mọi sở thích style đều đáng được tự động hóa. Có những quy ước nên được diễn đạt ở mức **review và thiết kế**, ví dụ:

- Tên phương thức phải diễn đạt ý định.
- Mã lỗi công khai phải ổn định và rõ nghĩa.
- Một thành phần nên có trách nhiệm dễ giải thích.
- Một nhánh xử lý cần làm rõ điều kiện cho phép/từ chối.
- Tác dụng phụ phải hiển thị và được kiểm thử.

Các tiêu chí này phụ thuộc vào ngữ cảnh nghiệp vụ, không thể thay bằng việc “định dạng xong là đạt chất lượng”.

Một nhóm trưởng thành thường kết hợp **formatter cho các chi tiết máy có thể quyết định**, **linter/checker cho các quy tắc tĩnh thích hợp** và **review con người cho ý nghĩa/hợp đồng**.

## 16. Cách viết mô tả PR để người review nhìn đúng vấn đề

Với PR format-only, mô tả nên ngắn và cụ thể:

~~~markdown
## Mục tiêu
Chuẩn hóa định dạng Java trong module Checkout theo cấu hình đã thống nhất.

## Phạm vi
- Chỉ file Java được liệt kê trong diff.
- Không thay logic, API, schema hoặc hợp đồng công khai.
- Không chỉnh generated code hay migration.

## Cách kiểm chứng
- Đã xem raw diff và rà các literal/import/annotation bị chạm.
- Build/test hiện có: ghi kết quả thực tế tại thời điểm chạy.
- Formatter check: ghi kết quả thực tế tại thời điểm chạy.

## Tách biệt
Sửa lỗi điều kiện miễn phí giao hàng tại ngưỡng 500.000 VND
sẽ được xử lý trong PR hành vi riêng, với test cho giá trị biên.
~~~

Với PR sửa hành vi, mô tả phải nêu **quy tắc cũ, quy tắc mới, test chứng minh và tác động đến client**. Không viết “chỉ là cleanup” nếu kết quả tại ngưỡng thay đổi.

Mẫu trên là **ví dụ để áp dụng**, không phải một báo cáo rằng build/test đã chạy trong bài học này.

## 17. Checklist trước khi merge một thay đổi quy ước

Đánh giá theo hai nhóm để không bỏ sót mục tiêu:

### A. Tính nhất quán và phạm vi

1. **Quy ước mới có được ghi lại không?** Người khác có thể tái lập kết quả formatter không?
2. **Phạm vi có đúng không?** Có file ngoài module hoặc generated code vô tình đổi không?
3. **Loại thay đổi có được phân loại đúng không?** Format-only có chứa rename, import cleanup, refactor hay sửa behavior không?
4. **Raw diff đã được review chưa?** Không chỉ xem chế độ bỏ qua whitespace.
5. **Các ngoại lệ có lý do không?** File nhạy whitespace hoặc dữ liệu được sinh đã được xử lý phù hợp?

### B. Bảo vệ hành vi và hợp đồng

6. **Baseline có được biết không?** Thất bại nào tồn tại trước khi format?
7. **Test/build sau format có cùng kết quả không?** Kết quả thực tế được ghi rõ.
8. **Có dữ liệu literal, text block hoặc cấu hình bị đổi không?**
9. **Có thay đổi public API, serialization, reflection hay annotation không?**
10. **Nếu có sửa hành vi riêng, test có xác định rõ kết quả kỳ vọng không?**
11. **Có thể review, rollback hoặc cherry-pick từng mục tiêu độc lập không?**
12. **Những người đang phát triển nhánh khác đã biết quy ước mới chưa?**

Một PR không nhất thiết phải đính kèm mọi số liệu nêu trên, nhưng người review cần có **bằng chứng tương xứng với độ rộng và rủi ro của thay đổi**.

## 18. Tự luyện qua các tình huống

### Tình huống A — Formatter che một thay đổi điều kiện

Một PR có 1.200 dòng thay đổi do formatter và một dòng đổi **quantity > 10** thành **quantity >= 10**. Mô tả PR chỉ ghi “normalize code style”.

**Câu hỏi:** Rủi ro nằm ở đâu và nên sửa quy trình ra sao?

**Gợi ý:** Thay toán tử là thay đổi hành vi ở biên 10. Cần tách khỏi commit/PR format-only, mô tả yêu cầu mới và có test cho 9, 10, 11. Nếu cần, review lại raw diff để bảo đảm không còn đổi logic khác bị ẩn.

### Tình huống B — Dùng git diff -w làm bằng chứng duy nhất

Người phát triển chạy một công cụ rồi thấy chế độ bỏ qua whitespace không hiển thị khác biệt. Họ kết luận “100% hành vi không đổi”.

**Câu hỏi:** Kết luận này có chắc chắn không?

**Gợi ý:** Không. Chế độ bỏ qua whitespace có thể che thay đổi ký tự khoảng trắng trong string literal hoặc dữ liệu nhạy với whitespace. Cần raw diff, kiểm tra loại file/literal, build/test và review.

### Tình huống C — Đổi tên public API trong PR format

Nhóm muốn thống nhất tên nên đổi **getStatus()** thành **currentStatus()** ở một API được module khác sử dụng, cùng lúc sửa khoảng trắng.

**Câu hỏi:** Đây có phải format-only không?

**Gợi ý:** Không. Đổi tên API có thể ảnh hưởng source/binary compatibility, reflection, docs và client. Hãy phân loại thành thay đổi hợp đồng/refactor, kiểm tra caller và phương án tương thích.

### Tình huống D — Sửa bug gấp giữa đợt chuẩn hóa

Đang chuẩn bị PR format 300 file thì phát hiện một lỗi phân quyền cần vá khẩn cấp trong 1 file.

**Câu hỏi:** Nên làm gì trước?

**Gợi ý:** Ưu tiên bản vá phân quyền nhỏ, có test và review bảo mật, không phụ thuộc vào việc merge đợt format lớn. Sau đó phối hợp merge/rebase và tiếp tục chuẩn hóa theo kế hoạch.

### Tình huống E — Mỗi IDE tạo một định dạng

Hai người thường xuyên commit những diff lặp lại do cùng file được format khác nhau giữa hai IDE.

**Câu hỏi:** Giải pháp chỉ là nhắc mọi người “cẩn thận hơn” hay không?

**Gợi ý:** Không. Cần quy ước có cấu hình phiên bản được quản lý, lệnh formatter thống nhất và CI kiểm tra để bảo đảm kết quả tái lập. Ownership của quy ước cũng cần rõ.

### Tình huống F — Test xanh nhưng text block đổi dữ liệu

Một formatter không phù hợp chỉnh thụt lề của Java text block chứa nội dung gửi tới dịch vụ ngoài. Test hiện có chỉ kiểm tra số lần gọi API, không kiểm tra payload.

**Câu hỏi:** Điều gì còn thiếu trong bằng chứng?

**Gợi ý:** Payload có thể thay đổi dù test xanh. Cần xem raw diff ở text block và test giá trị nội dung/contract với bên nhận, đồng thời loại trừ hoặc cấu hình formatter đúng.

---

**Ghi nhớ:** **Tính nhất quán giúp đọc và bảo trì mã, nhưng cách thay đổi quy ước cũng phải đáng tin cậy.** Hãy tách **format-only**, **refactor**, **thay đổi hợp đồng** và **sửa hành vi** thành các phạm vi có thể review; dùng formatter thống nhất; xem raw diff; xác minh bằng test và kiểm tra những vùng nhạy cảm. Khi nhiễu định dạng được tách khỏi thay đổi chức năng, người review dễ thấy **điều gì thực sự đổi, vì sao đổi và bằng chứng nào chứng minh nó đúng**.
