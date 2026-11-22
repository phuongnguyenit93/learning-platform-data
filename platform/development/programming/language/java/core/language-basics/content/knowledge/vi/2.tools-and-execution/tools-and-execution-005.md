# Chạy chương trình một tệp nguồn trong Java

Bạn vừa viết một chương trình Java nhỏ trong tệp `.java` và muốn xem ngay kết quả, nhưng chưa cần tạo thư mục `.class` hoặc cấu hình dự án. Từ **JDK 11**, Java hỗ trợ **source-file mode**: dùng lệnh `java` trỏ trực tiếp tới tệp nguồn. Trên **JDK 17 trở lên**, có thể chạy:

~~~bash
java QuickTotal.java 3 125000
~~~

Java launcher sẽ biên dịch mã nguồn trong bộ nhớ và chạy chương trình. Với cách chạy này, bạn **không phải gọi `javac` trước** và không có tệp `QuickTotal.class` được tạo trên đĩa chỉ bởi lệnh trên.

Bài học này hướng dẫn cách dùng chế độ đó, những tình huống phù hợp và điểm khác với quy trình biên dịch truyền thống.

## 1. Hai cách chạy một chương trình Java

Giả sử bạn có một tệp `QuickTotal.java` khai báo lớp `QuickTotal` với phương thức `main`.

| Cách | Lệnh | Tệp `.class` trên đĩa? | Thích hợp khi nào? |
| --- | --- | --- | --- |
| **Chạy trực tiếp nguồn** | `java QuickTotal.java` | Không tạo bởi lần chạy source-file mode | Thử nhanh một chương trình nguồn nhỏ |
| **Biên dịch rồi chạy** | `javac QuickTotal.java` rồi `java QuickTotal` | Có, sau khi biên dịch | Muốn kiểm soát sản phẩm build, triển khai hoặc dùng trong dự án lớn hơn |

Điểm quan trọng là **lệnh `java` có hai cách hiểu khác nhau**:

- `java QuickTotal.java`: đối số đầu là **đường dẫn tệp nguồn**; launcher dùng source-file mode.
- `java QuickTotal`: đối số đầu là **tên lớp**; JVM phải tìm bytecode của lớp qua classpath/module path thích hợp.

Không được thay `QuickTotal.java` bằng `QuickTotal.class` trong lệnh chạy lớp. Tên file nguồn và tên lớp là hai khái niệm khác nhau.

### Bên trong source-file mode diễn ra gì?

~~~mermaid
flowchart TD
    A["QuickTotal.java"] --> B["Lệnh java QuickTotal.java"]
    B --> C["Biên dịch mã nguồn trong bộ nhớ"]
    C --> D{"Mã có lỗi biên dịch?"}
    D -->|Có| E["In chẩn đoán và không chạy main"]
    D -->|Không| F["Khởi động main trong JVM"]
    F --> G["In kết quả hoặc báo lỗi lúc chạy"]
~~~

Vì việc biên dịch diễn ra khi chạy, lỗi cú pháp hay lỗi kiểu dữ liệu vẫn được phát hiện. Không tạo `.class` trên đĩa **không có nghĩa Java bỏ qua bước biên dịch**.

## 2. Kiểm tra JDK trước khi bắt đầu

Mở **PowerShell (Windows)** hoặc **Bash (Linux)**:

~~~bash
java -version
javac -version
~~~

Đầu ra cần cho biết bạn đang sử dụng JDK 17 trở lên (hoặc một phiên bản hỗ trợ tương ứng). Cách chạy nguồn trực tiếp bắt đầu được hỗ trợ từ JDK 11; ở đây ta dùng JDK 17+ để thống nhất môi trường học.

Nếu terminal báo không tìm thấy `java` hoặc `javac`:

1. Xác minh đã cài JDK và mở lại terminal sau khi cài hoặc đổi `PATH`.
2. **Windows PowerShell:** dùng `Get-Command java, javac` để xem chương trình được tìm thấy ở đâu.
3. **Linux:** dùng `command -v java` và `command -v javac`.
4. Khi nhiều JDK cùng tồn tại, cần bảo đảm lệnh `java` đang sử dụng phiên bản mong muốn.

Source-file mode chạy từ lệnh `java`, nhưng có JDK đầy đủ sẽ hữu ích khi bạn muốn so sánh với cách dùng `javac` ở phần sau.

## 3. Tạo tệp Java cho ví dụ

Mở một thư mục thực hành tùy chọn trong terminal. Có thể tạo thư mục bằng:

**PowerShell (Windows):**

~~~powershell
New-Item -ItemType Directory -Force -Path quick-java | Out-Null
Set-Location quick-java
~~~

**Bash (Linux):**

~~~bash
mkdir -p quick-java
cd quick-java
~~~

Dùng trình soạn thảo văn bản để tạo tệp chính xác tên **`QuickTotal.java`**, lưu dưới dạng văn bản UTF-8. Trên Windows, kiểm tra tệp không vô tình trở thành `QuickTotal.java.txt`.

Bài toán: nhận **số lượng hàng** và **đơn giá tính bằng VND nguyên** qua đối số dòng lệnh; in thành tiền. Số lượng phải lớn hơn 0, đơn giá không âm; khi phép nhân vượt miền `long`, phải báo lỗi thay vì âm thầm dùng kết quả tràn.

Nội dung hoàn chỉnh:

~~~java
public class QuickTotal {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.out.println(
                    "Cach dung: java QuickTotal.java <soLuong> <donGiaVnd>");
            return;
        }

        try {
            int quantity = Integer.parseInt(args[0]);
            long unitPriceVnd = Long.parseLong(args[1]);

            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "So luong phai lon hon 0");
            }
            if (unitPriceVnd < 0) {
                throw new IllegalArgumentException(
                        "Don gia khong duoc am");
            }

            long totalVnd = Math.multiplyExact(
                    (long) quantity, unitPriceVnd);

            System.out.println("So luong: " + quantity);
            System.out.println("Don gia: " + unitPriceVnd + " VND");
            System.out.println("Thanh tien: " + totalVnd + " VND");
        } catch (NumberFormatException ex) {
            System.out.println("Loi: Dau vao phai la so nguyen hop le");
        } catch (IllegalArgumentException ex) {
            System.out.println("Loi: " + ex.getMessage());
        } catch (ArithmeticException ex) {
            System.out.println("Loi: Ket qua vuot mien long");
        }
    }
}
~~~

### Vì sao đoạn mã này hoạt động?

- `public class QuickTotal` định nghĩa lớp sẽ chạy. Ví dụ dùng tệp `QuickTotal.java` trùng tên lớp công khai để có thể chạy bằng **cả source-file mode lẫn `javac QuickTotal.java` truyền thống**. Riêng source-file mode không buộc tên tệp trùng tên lớp `public`: launcher chạy lớp top-level đầu tiên trong tệp, nên lớp đó phải có `main` phù hợp. Với biên dịch truyền thống bằng `javac`, lớp top-level `public` vẫn phải nằm trong tệp cùng tên.
- `main(String[] args)` là điểm bắt đầu; chuỗi sau tên tệp nguồn trở thành các phần tử của mảng `args`.
- `Integer.parseInt` đọc số lượng; `Long.parseLong` đọc đơn giá. Cả hai đều có thể ném `NumberFormatException` khi chuỗi sai định dạng hoặc ngoài miền số.
- `quantity <= 0` và `unitPriceVnd < 0` thực thi các quy tắc đầu vào đã xác định.
- `Math.multiplyExact` trả về tích dạng `long` và ném `ArithmeticException` nếu tràn `long`, giúp tránh kết quả sai âm thầm.
- `NumberFormatException` là lớp con của `IllegalArgumentException` nên phải được bắt trước nhánh `IllegalArgumentException` tổng quát.
- Phần mã nguồn sử dụng các chuỗi thông báo ASCII để kết quả nhất quán giữa terminal có cấu hình encoding khác nhau.

Đây là một tệp nguồn độc lập: không cần thư viện ngoài, file cấu hình build hoặc class thứ hai.

## 4. Chạy trực tiếp với `java TenTep.java`

Trong thư mục chứa `QuickTotal.java`, chạy:

~~~bash
java QuickTotal.java 3 125000
~~~

Kết quả dự kiến:

~~~text
So luong: 3
Don gia: 125000 VND
Thanh tien: 375000 VND
~~~

Diễn giải: `3 × 125000 = 375000`. Khi dùng source-file mode, bạn không phải tạo tệp `.class` trên đĩa và không cần chạy `javac` riêng.

Thử chạy lại với đầu vào khác:

~~~bash
java QuickTotal.java 2 45000
~~~

~~~text
So luong: 2
Don gia: 45000 VND
Thanh tien: 90000 VND
~~~

Nếu sửa nội dung `QuickTotal.java` rồi lưu tệp, lần gọi `java QuickTotal.java` tiếp theo sẽ dùng **mã nguồn mới**. Đây là một điểm thuận tiện khi thực hành chương trình nhỏ.

### Khi bạn đang ở thư mục cha

Nếu lưu tại `quick-java/QuickTotal.java` nhưng đứng ở thư mục cha của `quick-java`, dùng:

~~~bash
java quick-java/QuickTotal.java 3 125000
~~~

Windows và Linux đều chấp nhận cách truyền đường dẫn này qua Java launcher. Nếu đường dẫn thực tế có dấu cách, đặt đường dẫn trong dấu nháy kép:

~~~bash
java "quick-java/QuickTotal.java" 3 125000
~~~

Dấu nháy bao quanh **đường dẫn**, còn `3` và `125000` là hai đối số riêng của chương trình.

## 5. Phân biệt các dạng lệnh dễ nhầm

| Lệnh | Điều xảy ra |
| --- | --- |
| `java QuickTotal.java 3 125000` | Chạy trực tiếp tệp nguồn |
| `java --source 17 QuickTotal.java 3 125000` | Chạy nguồn và yêu cầu mức ngôn ngữ Java 17 |
| `javac QuickTotal.java` | Biên dịch thành `QuickTotal.class` trong thư mục hiện tại |
| `java QuickTotal 3 125000` | Chạy bytecode của lớp `QuickTotal` qua classpath hiện tại |
| `java QuickTotal.class` | Không phải cách gọi lớp đúng; launcher không lấy tên tệp `.class` làm tên lớp |
| `javac -d out QuickTotal.java` | Đặt `QuickTotal.class` vào thư mục `out` (cần có thư mục đích phù hợp) |
| `java -cp out QuickTotal 3 125000` | Chạy lớp đã biên dịch từ thư mục `out` |

Tùy chọn `--source 17` hữu ích khi bạn muốn yêu cầu chế độ ngôn ngữ cụ thể. Nếu JDK đang dùng hỗ trợ Java 17, ví dụ sau cũng hợp lệ:

~~~bash
java --source 17 QuickTotal.java 3 125000
~~~

Đừng nhầm `--source 17` với `javac --release 17`. Lệnh `javac --release` dành cho biên dịch tạo bytecode nhắm tới phiên bản Java được hỗ trợ và các API nền tảng của release đó; source-file mode trong bài này dùng launcher `java` để thực thi trực tiếp.

## 6. Kiểm tra đầu vào sai và trường hợp biên

Hãy thử từng lệnh; khi dữ liệu sai, chương trình in thông báo lỗi đã viết trong mã:

| Lệnh | Kết quả/điểm cần kiểm tra |
| --- | --- |
| `java QuickTotal.java 1 0` | Thành tiền 0 VND |
| `java QuickTotal.java 2 100` | Thành tiền 200 VND |
| `java QuickTotal.java 0 100` | Báo số lượng phải lớn hơn 0 |
| `java QuickTotal.java -2 100` | Báo số lượng không hợp lệ |
| `java QuickTotal.java 2 -1` | Báo đơn giá không được âm |
| `java QuickTotal.java abc 100` | Báo đầu vào không phải số nguyên hợp lệ |
| `java QuickTotal.java 2 10.5` | Báo lỗi vì phiên bản này yêu cầu VND nguyên |
| `java QuickTotal.java 3` | In hướng dẫn sử dụng vì thiếu đối số |
| `java QuickTotal.java 2 9223372036854775807` | Báo kết quả vượt miền `long` |
| `java QuickTotal.java 2147483648 1` | Báo lỗi số lượng vượt miền `int` |

**Hai điểm biên quan trọng:**

1. `quantity = 1` được chấp nhận nhưng `quantity = 0` bị từ chối — vì bài toán yêu cầu lớn hơn 0.
2. Kết quả đúng của phép nhân có thể vượt miền `long` dù mỗi đầu vào được parse thành công. Kiểm tra kiểu không loại bỏ nhu cầu phát hiện tràn khi chạy.

`javac` hoặc bước biên dịch trong bộ nhớ sẽ kiểm tra cú pháp và kiểu, nhưng **không tự quyết định** số lượng bằng 0 có hợp lệ hay không; đó là quy tắc bạn viết trong chương trình.

## 7. Lỗi hay gặp với chế độ chạy trực tiếp

### Lỗi 1: Không tìm thấy hoặc không đọc được tệp nguồn

Nếu chạy `java QuickTotal.java ...` nhưng đường dẫn không trỏ tới tệp nguồn tồn tại và có thể đọc được, launcher thất bại **trước khi thực thi `main`**. Thông báo phụ thuộc JDK và cách launcher phân tích đối số; không nên chép một mẫu lỗi về `main` để kết luận rằng tệp đã bị thiếu.

Hãy kiểm tra theo thứ tự:

- Thư mục làm việc hiện tại là đâu? Tệp `QuickTotal.java` có thực sự ở đó không?
- Nếu tệp nằm trong thư mục con, đã truyền đúng đường dẫn (ví dụ `java quick-java/QuickTotal.java 3 125000`) chưa?
- Có vô tình lưu thành `QuickTotal.java.txt`, sai chữ hoa/thường của đường dẫn hoặc không có quyền đọc không?
- Nếu nguồn được tìm thấy nhưng launcher báo **không có `main`**, hãy kiểm tra chữ ký `main` của **lớp top-level đầu tiên** trong tệp. Đó là lỗi điểm vào chương trình, **không phải bằng chứng tệp nguồn không tồn tại**.

**PowerShell:** `Get-Location` và `Get-ChildItem`. **Linux:** `pwd` và `ls`.

### Lỗi 2: Chạy tên lớp thay vì tệp nguồn

~~~bash
java QuickTotal
~~~

Lệnh trên yêu cầu tìm **lớp đã biên dịch**. Nếu bạn chỉ có `QuickTotal.java`, JVM có thể báo không tìm thấy lớp. Muốn chạy nguồn trực tiếp, dùng:

~~~bash
java QuickTotal.java
~~~

Chạy không đủ hai đối số vẫn biên dịch và vào `main`, nhưng ví dụ sẽ in dòng hướng dẫn sử dụng. Điều này khác với lỗi compiler.

### Lỗi 3: Lỗi cú pháp hoặc kiểu ở nguồn

Nếu vô tình sửa:

~~~java
int quantity = "ba"; // Không hợp lệ: String không gán trực tiếp cho int.
~~~

Source-file mode vẫn thực hiện bước biên dịch và báo lỗi. **`main` chưa được chạy**, vì mã chưa hợp lệ. Sau khi sửa `int quantity = 3;`, bạn có thể gọi lại lệnh `java QuickTotal.java ...` ngay.

### Lỗi 4: JVM cũ hoặc công cụ khác phiên bản

JDK 8 không hỗ trợ kiểu chạy `java File.java`. Khi đó cần nâng lên phiên bản được hỗ trợ (bài này chọn JDK 17+), hoặc dùng `javac` rồi chạy `java TenLop` theo quy trình truyền thống.

Kiểm tra `java -version` nếu gặp lỗi chế độ chạy tệp nguồn.

## 8. Khi nào nên dùng source-file mode?

**Nên dùng** khi:

- Thực hành ngôn ngữ Java bằng một tệp nhỏ.
- Viết ví dụ thuật toán, kiểm tra thư viện chuẩn hoặc thử nhanh một giả thuyết.
- Muốn sửa rồi chạy lại mà không cần quản lý tệp build đầu ra.

**Cân nhắc chuyển sang biên dịch/build truyền thống** khi:

- Chương trình có nhiều tệp nguồn và phụ thuộc cần quản lý rõ.
- Bạn muốn kiểm soát quá trình đóng gói, kiểm thử tự động hoặc phiên bản bytecode để triển khai.
- Cần lặp lại build trong CI, tích hợp JAR hoặc công cụ như Maven/Gradle.
- Muốn tái sử dụng các tệp `.class` đã biên dịch thay vì xử lý tệp nguồn mỗi lần chạy.

Cơ chế source-file mode có thể làm việc với các lớp/phụ thuộc đã có trong classpath và có những quy tắc chi tiết khi mã nguồn chứa nhiều lớp. Tuy nhiên, bài thực hành này chỉ sử dụng **một tệp nguồn tự đủ** để tránh phải cấu hình thêm.

## 9. Bài tập ngắn

**Bài 1.** Chạy `java QuickTotal.java 4 75000`. Dự đoán kết quả thành tiền trước khi chạy.

*Đáp án:* `300000 VND`.

**Bài 2.** Sửa dòng in `"Thanh tien:"` thành `"Tong tien:"`, lưu tệp rồi chạy nguồn trực tiếp. Có cần chạy `javac` riêng không?

*Đáp án:* Không. Khi thực thi `java QuickTotal.java`, launcher sẽ dùng mã nguồn đã lưu.

**Bài 3.** Chạy thử lần lượt `java QuickTotal.java 0 1`, `java QuickTotal.java 1 -1` và `java QuickTotal.java one 1`. Xác định ca nào thất bại khi **chuyển chuỗi thành số**, ca nào bị từ chối do **quy tắc bài toán**.

*Đáp án:* `one` không parse được; 0 và −1 parse được nhưng bị từ chối theo quy tắc nghiệp vụ.

**Bài 4.** Biên dịch truyền thống bằng `javac QuickTotal.java`, sau đó chạy `java QuickTotal 3 125000`. Giải thích vì sao câu lệnh `java` lần này **không có `.java`**.

*Đáp án:* JVM đang tìm tên lớp từ bytecode đã được `javac` tạo trên đĩa, không chạy trực tiếp tệp nguồn.

### Checklist hoàn thành

- [ ] `java -version` cho thấy phiên bản hỗ trợ source-file mode (bài dùng JDK 17+).
- [ ] Có tệp `QuickTotal.java` đúng tên và thư mục.
- [ ] Chạy được `java QuickTotal.java 3 125000` và nhận đúng `375000 VND`.
- [ ] Tự sửa và chạy lại mã nguồn mà không cần lệnh `javac` riêng.
- [ ] Phân biệt được lỗi biên dịch và lỗi dữ liệu lúc chạy.
- [ ] Biết khi nào chuyển sang `javac` / classpath / công cụ build.

## Ghi nhớ

**`java TenTep.java` chạy mã nguồn trực tiếp bằng cách biên dịch trong bộ nhớ rồi thực thi**, thích hợp để học và thử nhanh một chương trình Java nhỏ. **`javac TenTep.java` rồi `java TenLop`** là quy trình tạo và chạy bytecode trên đĩa. Học đúng hai cách sẽ giúp bạn hiểu mình đang chạy **tệp nguồn** hay **lớp đã biên dịch**, đồng thời xử lý lỗi chính xác hơn.
