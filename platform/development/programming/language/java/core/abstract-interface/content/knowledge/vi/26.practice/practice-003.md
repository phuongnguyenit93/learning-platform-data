# Thực hiện Template Method cho quy trình nhập dữ liệu

Template Method là mẫu thiết kế hành vi trong đó lớp cha định nghĩa **bộ khung cố định của một thuật toán**, còn các lớp con tùy biến một số bước cụ thể. Với quy trình nhập dữ liệu, lớp cha có thể quyết định thứ tự kiểm tra nguồn, đọc dữ liệu, phân tích từng dòng, xác thực bản ghi, lưu kết quả và thông báo hoàn tất. Mỗi định dạng như CSV hoặc TSV chỉ cần cung cấp cách phân tích dòng và cách lưu phù hợp.

Mẫu này hữu ích khi nhiều quy trình nhập dữ liệu có cùng các bước và thứ tự, nhưng khác nhau ở một vài chi tiết. Nó giúp tránh việc mỗi lớp tự viết lại toàn bộ quy trình và vô tình bỏ qua một bước quan trọng.

## 1. Cấu trúc Template Method trong bài toán nhập dữ liệu

Trong ví dụ này, `DataImporter` là lớp cha trừu tượng. Phương thức `importFile()` là **Template Method** và được khai báo `final`, vì vậy lớp con không thể thay đổi trình tự các bước.

Quy trình được giữ nhất quán như sau:

1. Kiểm tra đường dẫn nguồn có trỏ tới tệp thông thường hay không.
2. Đọc các dòng từ tệp bằng UTF-8.
3. Bỏ qua dòng trống; phân tích từng dòng thành bản ghi.
4. Xác thực các trường của bản ghi.
5. Gọi bước lưu dữ liệu do lớp con triển khai.
6. Báo số bản ghi đã nhập thành công.

`parseLine()` và `persist()` là các bước trừu tượng buộc lớp con triển khai. `validateSource()`, `readSource()`, `validateRecord()` và `afterImport()` là các hook có cài đặt mặc định mà lớp con có thể ghi đè khi cần. Không phải hook nào cũng cần được ghi đè.

## 2. Ví dụ Java 17+ chạy độc lập

Ví dụ gồm `CsvImporter` và `TsvImporter`. Cả hai sử dụng chung thuật toán `importFile()`, nhưng phân tích dữ liệu theo dấu phẩy hoặc ký tự tab và thực hiện bước lưu riêng. Chương trình tự tạo các tệp ví dụ tạm thời rồi xóa chúng sau khi chạy.

Lưu đoạn mã dưới đây vào `TemplateMethodImportDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class TemplateMethodImportDemo {
    private record ImportRecord(String name, String email) {}

    private abstract static class DataImporter {
        public final void importFile(Path file) throws IOException {
            Objects.requireNonNull(file, "file");
            validateSource(file);
            System.out.println("Start import: " + file.getFileName());
            List<String> lines = readSource(file);
            List<ImportRecord> records = new ArrayList<>();
            for (int i = 0; i < lines.size(); i++) {
                String line = lines.get(i);
                if (line.isBlank()) continue;
                ImportRecord record = parseLine(line, i + 1);
                validateRecord(record, i + 1);
                records.add(record);
            }
            persist(List.copyOf(records));
            afterImport(records.size());
        }

        protected void validateSource(Path file) {
            if (!Files.isRegularFile(file)) {
                throw new IllegalArgumentException("Input file not found: " + file);
            }
        }
        protected List<String> readSource(Path file) throws IOException {
            return Files.readAllLines(file, StandardCharsets.UTF_8);
        }
        protected abstract ImportRecord parseLine(String line, int lineNumber);
        protected void validateRecord(ImportRecord record, int lineNumber) {
            if (record.name().isBlank() || !record.email().contains("@")) {
                throw new IllegalArgumentException("Invalid record at line " + lineNumber);
            }
        }
        protected abstract void persist(List<ImportRecord> records);
        protected void afterImport(int count) {
            System.out.println("Import complete: " + count + " records");
        }
    }

    private static final class CsvImporter extends DataImporter {
        @Override protected ImportRecord parseLine(String line, int lineNumber) {
            String[] fields = line.split(",", -1);
            if (fields.length != 2) {
                throw new IllegalArgumentException("Expected 2 CSV fields at line " + lineNumber);
            }
            return new ImportRecord(fields[0].trim(), fields[1].trim());
        }
        @Override protected void persist(List<ImportRecord> records) {
            System.out.println("Persisting CSV records:");
            for (ImportRecord record : records) {
                System.out.println("  " + record.name() + " -> " + record.email());
            }
        }
    }

    private static final class TsvImporter extends DataImporter {
        @Override protected ImportRecord parseLine(String line, int lineNumber) {
            String[] fields = line.split("\\t", -1);
            if (fields.length != 2) {
                throw new IllegalArgumentException("Expected 2 TSV fields at line " + lineNumber);
            }
            return new ImportRecord(fields[0].trim(), fields[1].trim());
        }
        @Override protected void persist(List<ImportRecord> records) {
            System.out.println("Persisting TSV records:");
            for (ImportRecord record : records) {
                System.out.println("  " + record.name() + " -> " + record.email());
            }
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("template-method-import-");
        Path csv = directory.resolve("people.csv");
        Path tsv = directory.resolve("people.tsv");
        try {
            Files.write(csv, List.of(
                "Alice,alice@example.com",
                "Bob,bob@example.com"
            ), StandardCharsets.UTF_8);
            Files.write(tsv, List.of(
                "Carol\tcarol@example.com"
            ), StandardCharsets.UTF_8);
            new CsvImporter().importFile(csv);
            new TsvImporter().importFile(tsv);
        } finally {
            Files.deleteIfExists(csv);
            Files.deleteIfExists(tsv);
            Files.deleteIfExists(directory);
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```text
javac TemplateMethodImportDemo.java
java TemplateMethodImportDemo
```

Đầu ra chính xác:

```text
Start import: people.csv
Persisting CSV records:
  Alice -> alice@example.com
  Bob -> bob@example.com
Import complete: 2 records
Start import: people.tsv
Persisting TSV records:
  Carol -> carol@example.com
Import complete: 1 records
```

## 3. Vì sao đây là Template Method?

Điểm quyết định là `importFile()` điều phối toàn bộ thuật toán và không cho lớp con ghi đè phương thức này. Cả hai importer đều phải đi qua kiểm tra nguồn, đọc tệp, phân tích, xác thực, lưu và hoàn tất theo cùng trình tự. Lớp con chỉ thay đổi những điểm mở rộng được thiết kế sẵn.

`parseLine()` là điểm mở rộng cần thiết vì mỗi định dạng có cú pháp riêng. `persist()` cho phép mỗi importer thay cách lưu dữ liệu; trong ví dụ, chúng in bản ghi ra màn hình để có thể quan sát. Trong ứng dụng thật, phần này có thể ghi vào cơ sở dữ liệu hoặc gửi dữ liệu tới một dịch vụ.

`validateRecord()` có logic mặc định dùng chung, nên cả CSV lẫn TSV đều phải có tên không rỗng và email chứa ký tự `@`. `afterImport()` cũng có mặc định dùng chung. Lớp con có thể mở rộng hook nếu cần thêm bước như ghi số liệu, nhưng nên gọi lại hành vi cha nếu hành vi đó vẫn cần thiết.

## 4. Cách áp dụng vào hệ thống thực tế

- Đặt trong lớp cha các bước thực sự giống nhau và thứ tự mà mọi quy trình phải tuân thủ, ví dụ xác minh nguồn, đọc, chuẩn hóa, xác thực và lưu.
- Tạo hook cho phần khác nhau giữa các định dạng, chẳng hạn phân tích dòng CSV, TSV hoặc một định dạng nội bộ.
- Truyền cấu hình qua constructor hoặc tham số khi khác biệt chỉ là dữ liệu cấu hình, như tên bảng hoặc quy tắc ánh xạ. Không cần tạo một lớp con cho mọi giá trị cấu hình.
- Xác định rõ xử lý lỗi: dừng toàn bộ khi một dòng không hợp lệ, bỏ qua dòng lỗi, hay gom lỗi để báo cáo cuối cùng. Đó là quyết định nghiệp vụ, không nên để hành vi phát sinh ngẫu nhiên.
- Nếu bước lưu cần giao dịch, hãy xác định ranh giới giao dịch ở mức quy trình để tránh nhập một phần dữ liệu ngoài ý muốn.

Ví dụ này dùng `split()` đơn giản nên chỉ minh họa nguyên tắc thiết kế. Nó chưa xử lý dấu phẩy nằm trong trường CSV được đặt trong dấu ngoặc kép, tiêu đề cột, mã hóa lỗi hay quy tắc email đầy đủ. Với CSV sản xuất, nên dùng thư viện phân tích CSV chuyên dụng và bổ sung chiến lược giao dịch, ghi log cùng báo cáo lỗi phù hợp.

## 5. Template Method so với cách viết lặp

Không dùng mẫu này, mỗi importer có thể tự viết một phương thức nhập riêng. Theo thời gian, một lớp có thể quên xác thực, lớp khác có thể lưu trước khi kiểm tra xong, và cách báo lỗi trở nên không nhất quán. Template Method tập trung phần trình tự vào một nơi để các triển khai chia sẻ quy tắc chung.

Tuy nhiên, không nên biến lớp cha thành một framework có quá nhiều hook. Nếu các quy trình khác nhau gần như hoàn toàn, hoặc cần kết hợp các bước theo nhiều cấu hình, composition với các đối tượng chiến lược có thể dễ thay đổi hơn. Dùng Template Method khi trình tự tổng thể tương đối ổn định và chỉ một số bước cần chuyên biệt hóa.

## 6. Lỗi thường gặp

1. **Cho phép lớp con ghi đè thuật toán chính.** Nếu thứ tự bước là bất biến của thiết kế, khai báo Template Method là `final` để lớp con không vô tình bỏ qua xác thực hoặc cleanup.
2. **Đặt mọi thứ vào lớp cha.** Chỉ giữ logic dùng chung trong lớp cha; hành vi riêng theo định dạng nên nằm ở hook hoặc lớp con thích hợp.
3. **Dùng hook nhưng không xác định hợp đồng.** Ghi rõ thời điểm hook chạy, dữ liệu nhận vào, lỗi có thể ném và liệu hook có được bỏ qua hay không.
4. **Xử lý lỗi không nhất quán.** Cần quyết định rõ khi một bản ghi lỗi thì dừng, tiếp tục, hay hoàn tác. Ví dụ này ném ngoại lệ và dừng quy trình khi dòng sai.
5. **Nhầm Template Method với Strategy.** Template Method dựa vào kế thừa và một khung thuật toán ở lớp cha; Strategy đóng gói một thuật toán hoặc chính sách có thể thay thế thông qua composition.

## 7. Checklist khi thiết kế

- Thuật toán có trình tự chung ổn định giữa các importer không?
- Phần nào bắt buộc phải giống nhau, và phần nào thực sự cần tùy biến?
- Template Method có nên là `final` để bảo vệ thứ tự không?
- Hook có tên rõ ràng, hợp đồng rõ ràng và phạm vi trách nhiệm nhỏ không?
- Quy tắc xác thực, lỗi, giao dịch và lưu dữ liệu đã được xác định chưa?
- Ví dụ đã kiểm thử ít nhất một định dạng hợp lệ và trường hợp đầu vào không hợp lệ chưa?

Khi các câu trả lời cho thấy quy trình có bộ khung chung nhưng khác nhau ở một số bước, Template Method giúp gom luồng điều khiển vào một nơi và giữ các phần chuyên biệt ở đúng điểm mở rộng.