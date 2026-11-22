# Điều chỉnh đầu ra bằng -quiet, -verbose, -debug và -silent

Khi chạy Apache Ant, terminal hiển thị thông tin về project, target, task, cảnh báo, lỗi và kết quả build. Với một build nhỏ, mức đầu ra mặc định thường đủ để theo dõi. Khi build có nhiều target hoặc chạy trên CI, log có thể quá dài; ngược lại, khi gặp lỗi khó tái hiện, thông tin mặc định có thể chưa đủ để tìm nguyên nhân.

Ant cung cấp bốn tùy chọn dòng lệnh để điều chỉnh lượng thông tin chẩn đoán: `-quiet`, `-silent`, `-verbose` và `-debug`. Chúng thay đổi mức log mà logger mặc định của Ant hiển thị. Chúng không thay đổi dependency giữa các target, không bỏ qua task và không tự thay đổi kết quả build.

## 1. Bốn mức đầu ra của Ant

| Tùy chọn | Viết tắt | Mục đích | Thông tin thường thấy |
|---|---|---|---|
| `-quiet` | `-q` | Giảm log thông thường | Cảnh báo và lỗi vẫn được hiển thị |
| `-silent` | `-S` | Giảm đầu ra xuống mức tối thiểu | Đầu ra của task và thông tin build thất bại |
| `-verbose` | `-v` | Hiển thị nhiều thông tin hơn mức mặc định | Thông tin thực thi target/task và các chi tiết verbose |
| `-debug` | `-d` | Hiển thị thông tin chẩn đoán sâu | Log debug nội bộ và chi tiết phục vụ truy vết |

Có thể hình dung mức độ chi tiết theo chiều tăng dần như sau:

```text
-silent   Chỉ đầu ra task và build failure
   ↓
-quiet    Giảm log; vẫn giữ warning và error
   ↓
default   Mức thông tin thông thường
   ↓
-verbose  Nhiều chi tiết thực thi hơn
   ↓
-debug    Thông tin chẩn đoán sâu nhất
```

Sơ đồ biểu diễn cách chọn mức log theo nhu cầu. `-silent` và `-debug` phục vụ hai mục đích rất khác nhau: một tùy chọn giảm tối đa log của Ant, tùy chọn còn lại mở rộng log để điều tra vấn đề.

## 2. Dùng -quiet khi chỉ cần kết quả và cảnh báo

`-quiet` yêu cầu Ant giảm lượng thông tin thông thường trên terminal. Các cảnh báo và lỗi vẫn được hiển thị, vì vậy đây là lựa chọn phù hợp khi build đã ổn định và người chạy chủ yếu cần biết có vấn đề cần chú ý hay không.

```bash
ant -quiet compile
```

Có thể dùng dạng viết tắt:

```bash
ant -q compile
```

Khi cần chạy nhiều target:

```bash
ant -q clean test jar
```

Ant vẫn thực hiện các target và task theo dependency đã khai báo. `-quiet` chỉ giảm thông tin được logger hiển thị; nếu task tự ghi nội dung ra standard output hoặc standard error thì nội dung đó vẫn có thể xuất hiện.

Nên dùng `-quiet` khi:

- Build chạy thường xuyên và log mặc định làm khó quan sát kết quả quan trọng.
- Muốn giảm log trong một lệnh CI nhưng vẫn giữ cảnh báo và lỗi của Ant.
- Chạy một target quen thuộc và không cần xem chi tiết từng bước.

Không nên dùng `-quiet` để che một lỗi đang điều tra. Khi cần biết task nào được chạy, property nào được sử dụng hoặc file nào được kiểm tra, hãy tăng mức log lên `-verbose`.

## 3. Dùng -silent khi muốn đầu ra tối thiểu

`-silent` yêu cầu Ant chỉ in đầu ra của task và thông tin về build thất bại. Đây là mức log tối thiểu trong bốn tùy chọn đang học.

```bash
ant -silent test
```

Hoặc dùng viết tắt:

```bash
ant -S test
```

Tùy chọn này hữu ích khi một task tự tạo đầu ra mà người chạy cần xem, nhưng không muốn nhìn các thông báo log thông thường của Ant. Ví dụ, một task có thể gọi chương trình bên ngoài và chương trình đó in kết quả ra terminal. `-silent` không có nghĩa là chặn mọi byte được ghi ra terminal; đầu ra do task hoặc tiến trình con tạo ra vẫn có thể xuất hiện.

`-silent` cũng có thể làm mất các cảnh báo của Ant mà người vận hành cần biết. Vì vậy, chỉ dùng mức này khi đã hiểu task nào tạo đầu ra và có lý do rõ ràng để ẩn log thông thường. Trong pipeline cần giữ cảnh báo để chẩn đoán, `-quiet` thường phù hợp hơn.

## 4. Dùng -verbose để xem chi tiết thực thi

`-verbose` yêu cầu Ant hiển thị nhiều thông tin hơn mức mặc định. Mức này hữu ích khi muốn biết target và task đang được thực hiện ra sao, hoặc muốn quan sát thêm thông tin mà chế độ mặc định không hiển thị.

```bash
ant -verbose compile
```

Dạng viết tắt:

```bash
ant -v compile
```

Khi một target có nhiều bước, log verbose giúp lần theo quá trình thực thi và nhận ra bước nào xuất hiện trước khi build thất bại. Nó cũng hữu ích khi tìm hiểu một build script mới hoặc xác minh Ant đang đi theo dependency dự kiến.

Ví dụ, nếu gọi:

```bash
ant -verbose jar
```

Ant sẽ chạy các dependency của `jar` trước rồi mới thực hiện target `jar`. Log verbose cung cấp thêm thông tin trong quá trình này. Nó không biến `jar` thành một target khác và cũng không bỏ qua các bước như compile hoặc test.

Nên dùng `-verbose` khi:

- Cần biết Ant đã đi qua những target nào.
- Muốn tìm hiểu vì sao một task được thực hiện hoặc vì sao một bước không tạo output như mong đợi.
- Cần thêm ngữ cảnh trước khi quyết định có phải bật log debug hay không.

Nếu log verbose vẫn chưa chỉ ra nguyên nhân, chuyển sang `-debug`.

## 5. Dùng -debug để điều tra lỗi sâu

`-debug` yêu cầu Ant in thông tin chẩn đoán ở mức chi tiết. Log có thể chứa thêm thông tin về quá trình cấu hình project, xử lý property, nạp task, classpath và hoạt động nội bộ của build. Nội dung cụ thể phụ thuộc phiên bản Ant, logger đang dùng và task được thực thi.

```bash
ant -debug test
```

Dạng viết tắt:

```bash
ant -d test
```

Hãy dùng `-debug` khi đã có dấu hiệu cho thấy log thông thường hoặc verbose chưa đủ để tìm nguyên nhân. Một số tình huống phù hợp:

- Ant không nạp được một task hoặc thư viện mở rộng.
- Property hoặc đường dẫn được mở rộng thành giá trị không như dự kiến.
- Classpath thiếu thành phần hoặc có vấn đề khi nạp class.
- Build thất bại trong một bước phức tạp và cần thêm dữ liệu để xác định điểm lỗi.

Log debug thường dài. Hãy xác định target đang lỗi, lưu log và tìm thông báo lỗi đầu tiên cùng các dòng ngay trước nó. Những lỗi xuất hiện sau đó có thể chỉ là hệ quả của lỗi ban đầu.

Log debug cũng có thể hiển thị đường dẫn nội bộ, giá trị cấu hình hoặc dữ liệu do task ghi ra. Trước khi chia sẻ log ra ngoài nhóm, hãy kiểm tra và che thông tin bí mật nếu có.

## 6. So sánh bằng cùng một target

Để thấy sự khác nhau, hãy dùng cùng một lệnh build và chỉ thay đổi tùy chọn đầu ra:

```bash
ant test
ant -quiet test
ant -silent test
ant -verbose test
ant -debug test
```

Các lệnh đều gọi target `test`. Nếu target `test` phụ thuộc `compile`, Ant vẫn thực hiện compile trước khi chạy test trong cả năm trường hợp. Điểm thay đổi là lượng thông tin logger hiển thị.

| Tình huống | Lựa chọn nên thử trước | Lý do |
|---|---|---|
| Chạy build thông thường | Không thêm tùy chọn | Mức mặc định cân bằng giữa thông tin và độ dài log |
| Log quá nhiều nhưng vẫn cần thấy warning | `-quiet` | Giảm thông tin thường, giữ cảnh báo và lỗi |
| Chỉ muốn thấy đầu ra task và build failure | `-silent` | Giảm log Ant xuống mức tối thiểu |
| Cần theo dõi quá trình thực thi | `-verbose` | Cung cấp thêm ngữ cảnh về target và task |
| Chưa tìm được nguyên nhân sau khi xem verbose | `-debug` | Bổ sung thông tin chẩn đoán sâu |

Không cần bật `-debug` cho mọi lần build. Mức log cao tạo ra nhiều dữ liệu hơn, khiến việc tìm thông báo liên quan khó hơn nếu chưa biết cần tìm gì.

## 7. Ghi log ra file để xem lại

Khi log verbose hoặc debug quá dài, có thể chuyển output của lệnh sang file để tìm kiếm và lưu làm bằng chứng chẩn đoán.

Trên shell Bash hoặc Windows Command Prompt:

```bash
ant -debug test > ant-debug.log 2>&1
```

Trên PowerShell:

```powershell
ant -debug test *> ant-debug.log
```

Sau đó có thể tìm từ khóa như `BUILD FAILED`, tên target, tên task hoặc thông báo lỗi của compiler. Việc chuyển hướng output của shell độc lập với tùy chọn log của Ant: `-debug` quyết định mức log Ant tạo ra, còn `>` hoặc `*>` quyết định nơi shell ghi các luồng output.

Nếu muốn giữ log thông thường cho lần chạy hàng ngày và chỉ tạo log debug khi gặp lỗi, hãy chạy lại đúng target với `-debug` sau khi ghi nhận lệnh và property đã dùng. Với lỗi chỉ xuất hiện trong một môi trường cụ thể, hãy giữ nguyên các tham số build liên quan để việc điều tra có thể tái hiện được.

## 8. Phân biệt log của Ant với output của task

Các tùy chọn trên chủ yếu điều chỉnh mức thông điệp của logger Ant. Một task cũng có thể tự ghi dữ liệu ra console hoặc khởi chạy chương trình con có output riêng. Do đó, `-quiet` hoặc `-silent` không bảo đảm terminal hoàn toàn trống.

Ví dụ task gọi chương trình Java:

```xml
<target name="run" depends="compile">
    <java classname="com.example.App"
          fork="true"
          failonerror="true">
        <classpath>
            <pathelement location="build/classes"/>
        </classpath>
    </java>
</target>
```

Thông báo do Ant ghi về việc chạy target/task chịu ảnh hưởng của mức log. Nội dung chương trình `App` in ra là output của chương trình được gọi và có thể vẫn xuất hiện khi dùng `-quiet` hoặc `-silent`.

Ngoài ra, nếu dự án cấu hình logger riêng bằng tùy chọn `-logger`, hoặc có listener tùy chỉnh, cách định dạng và xử lý thông điệp có thể khác logger mặc định. Khi kết quả quan sát không giống mong đợi, hãy kiểm tra cấu hình logger của build trước khi kết luận tùy chọn dòng lệnh không hoạt động.

## 9. Quy trình chọn mức log khi xử lý sự cố

Có thể áp dụng một quy trình ngắn để tránh tạo log lớn hơn mức cần thiết:

1. Chạy target với mức mặc định để xác định build có thành công hay không và ghi nhận thông báo lỗi.
2. Nếu log quá dài trong lần chạy bình thường, thử `-quiet`; nếu chỉ cần output task và thông tin build failure, cân nhắc `-silent`.
3. Nếu chưa rõ Ant đã thực hiện những bước nào, chạy lại với `-verbose`.
4. Nếu verbose chưa đủ thông tin, chạy lại target với `-debug` và lưu log vào file.
5. Tìm lỗi đầu tiên, kiểm tra các dòng log ngay trước lỗi và đối chiếu với target/task tương ứng trong `build.xml`.
6. Sau khi sửa nguyên nhân, chạy lại test hoặc target bị ảnh hưởng ở mức log phù hợp để xác nhận kết quả.

Không nên thay đổi dependency giữa các target chỉ để làm log ngắn hơn. Đầu ra được điều chỉnh bằng tùy chọn dòng lệnh; thứ tự build vẫn phải được mô tả trong `depends` và cấu trúc target.

## 10. Bài tập thực hành

Tạo một build script có các target `init`, `compile`, `test`, `jar`, `clean` và một target tổng hợp `build`. Sau đó thực hiện các bài tập:

| Bài tập | Lệnh hoặc thao tác | Điều cần quan sát |
|---|---|---|
| 1. Mức mặc định | `ant build` | Log thông thường và kết quả build |
| 2. Quiet | `ant -q build` | Log giảm nhưng warning/error vẫn được giữ |
| 3. Silent | `ant -S test` | Chỉ còn output task và thông tin build failure |
| 4. Verbose | `ant -v compile` | Thông tin thực thi chi tiết hơn |
| 5. Debug | `ant -d test` | Thông tin chẩn đoán sâu hơn |
| 6. Lưu log | `ant -debug test > ant-debug.log 2>&1` | Có thể mở và tìm kiếm log đã lưu |
| 7. So sánh kết quả | Chạy cùng target với các mức khác nhau | Target và kết quả build không đổi chỉ vì mức log |

Để kiểm tra việc truyền lỗi, cố tình tạo một test thất bại rồi chạy `ant -q build` và `ant -d build`. Quan sát xem build có báo thất bại ở cả hai lần hay không. Mức log không được dùng để biến một test thất bại thành thành công.

Sau bài thực hành, người học cần chọn được mức log phù hợp cho ba mục đích: chạy build thường ngày, giảm độ dài log và điều tra lỗi khó. Cũng cần giải thích được vì sao output của task có thể vẫn xuất hiện khi Ant đang ở chế độ `-quiet` hoặc `-silent`.
