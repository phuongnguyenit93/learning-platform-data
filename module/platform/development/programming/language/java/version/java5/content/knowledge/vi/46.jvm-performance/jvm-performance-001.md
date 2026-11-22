# Class Data Sharing và chia sẻ siêu dữ liệu lớp

Khi nhiều tiến trình Java chạy cùng bộ lớp, mỗi JVM có thể phải lặp lại một phần công việc đọc và chuẩn bị dữ liệu lớp. **Class Data Sharing (CDS)** lưu dữ liệu lớp đã được chuẩn bị vào một tệp archive để JVM có thể tái sử dụng.

Mục tiêu chính là giảm chi phí khởi động và giảm phần bộ nhớ bị nhân bản giữa các JVM phù hợp. CDS là tính năng của cách triển khai JVM như HotSpot; nó không phải cơ chế để các ứng dụng dùng chung biến tĩnh hoặc đối tượng nghiệp vụ đang thay đổi.

## 1. Mô hình: chuẩn bị một lần, dùng lại ở lần chạy sau

Có thể hình dung đường đi thông thường:

```text
Tệp lớp trong JDK/JAR
        |
        v
Đọc và xử lý dữ liệu lớp trong JVM
        |
        v
Dữ liệu cần cho việc chạy ứng dụng
```

Với CDS:

```text
Lượt chuẩn bị
    lớp được nạp -> dữ liệu phù hợp -> archive

Các lượt chạy sau
    archive -> ánh xạ bộ nhớ -> tái sử dụng dữ liệu đã chuẩn bị
```

Một phần archive có thể được hệ điều hành ánh xạ chỉ đọc để nhiều tiến trình JVM trên cùng máy dùng chung các trang nhớ. Lợi ích không chỉ là đọc lại cùng tệp nhanh hơn: dữ liệu đã có dạng phù hợp cho JVM, giúp tránh lặp lại một phần công việc xử lý.

Xem [mô tả CDS trong tài liệu JVM](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html).

### Chia sẻ dữ liệu lớp không đồng nghĩa chia sẻ trạng thái ứng dụng

```text
                   archive dùng chung
                    /             \
                   v               v
                JVM A            JVM B
             heap riêng       heap riêng
             static riêng     static riêng
```

Hai JVM vẫn là hai tiến trình độc lập. Bộ đếm tĩnh, phiên đăng nhập, kết nối mạng và đối tượng nghiệp vụ của JVM A không tự xuất hiện trong JVM B.

CDS chủ yếu được giải thích qua siêu dữ liệu lớp; một số cơ chế archive của HotSpot còn có thể chứa các đối tượng heap được hỗ trợ. Điều đó không biến CDS thành ảnh chụp tùy ý toàn bộ heap hay một cơ chế khôi phục phiên làm việc của ứng dụng.

## 2. CDS mặc định, AppCDS và archive động

| Khái niệm | Cách hiểu |
| --- | --- |
| Archive mặc định của JDK | Dữ liệu chuẩn bị sẵn cho các lớp nền tảng, nếu bản phân phối cung cấp |
| AppCDS | Mở rộng việc archive cho các lớp ứng dụng phù hợp |
| Archive động | Thu thập các lớp phù hợp trong một lượt chạy, ghi phần bổ sung khi JVM kết thúc |

Đừng thấy JVM đã bật CDS mặc định rồi suy ra lớp ứng dụng của mình đã nằm trong archive. Ví dụ bên dưới chủ động tạo archive cho ứng dụng và kiểm tra nguồn nạp của từng lớp.

Tài liệu Oracle JDK mô tả archive mặc định và AppCDS trong [Class Data Sharing](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html). Cách tạo archive động bằng `ArchiveClassesAtExit` vẫn được tài liệu JDK 25 hỗ trợ; xem [hướng dẫn tạo CDS archive](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#manually-creating-cds-archives).

Archive động thường bổ sung trên một archive nền, chẳng hạn archive mặc định của cùng JDK. Vì thế, không nên xem tệp bổ sung là một gói độc lập dùng được với mọi JDK.

## 3. Ví dụ hoàn chỉnh: chứng minh lớp ứng dụng được nạp từ archive

Ví dụ dùng JDK HotSpot có hỗ trợ CDS, JDK 17 trở lên. Các lệnh đã được kiểm chứng trên OpenJDK 24.0.2 Zulu 64 bit. Mã nguồn biên dịch với `--release 17`.

### 3.1. Mã ứng dụng

Tạo tệp `src/demo/Main.java` trong một thư mục riêng:

```java
package demo;

import java.util.List;

public class Main {
    static {
        System.out.println("app.init");
    }

    public static void main(String[] args) {
        List<String> topics = List.of("classes", "metadata", "archive");
        System.out.println("hello=" + Greeting.message());
        System.out.println("topics=" + topics.size());
    }
}

class Greeting {
    static String message() {
        return "CDS";
    }
}
```

Hai lớp `demo.Main` và `demo.Greeting` giúp ta kiểm tra dữ liệu ứng dụng thay vì chỉ nhìn thấy các lớp JDK được chia sẻ sẵn. Dòng `app.init` dùng để quan sát khối khởi tạo tĩnh.

### 3.2. Biên dịch và đóng gói JAR

Lưu mã UTF-8 không BOM. Mở PowerShell tại thư mục ví dụ, có `java`, `javac`, `jar` trong `PATH`:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/Main.java
jar --create --file app.jar --main-class demo.Main -C out .
```

Chỉ tiếp tục khi từng lệnh thành công.

Dùng JAR giúp bố trí classpath ổn định và phù hợp cho archive. Đừng thay trực tiếp `-jar app.jar` trong quy trình bằng một thư mục lớp đang liên tục thay đổi rồi mặc định archive vẫn hợp lệ.

### 3.3. Chạy đối chứng khi tắt chia sẻ

```powershell
java -Xshare:off -jar app.jar
```

Stdout ứng dụng:

```text
app.init
hello=CDS
topics=3
```

Lượt này chỉ là đối chứng hành vi. Nó chưa đo hiệu năng và không tạo archive ứng dụng.

### 3.4. Tạo archive động bằng một lượt chạy

```powershell
java -Xshare:auto '-XX:ArchiveClassesAtExit=app.jsa' -jar app.jar
```

Ứng dụng vẫn in:

```text
app.init
hello=CDS
topics=3
```

Khi JVM kết thúc bình thường, archive động được ghi vào `app.jsa`. Kiểm tra sự tồn tại:

```powershell
Get-Item -LiteralPath app.jsa
```

Trong lượt kiểm chứng, tệp được tạo thành công. Không có kích thước archive cố định phải giống nhau trên mọi phiên bản JDK.

Lượt chuẩn bị chỉ thu thập những lớp được nạp và đủ điều kiện archive trong tình huống đã chạy. Nếu một nhánh của ứng dụng không được thực hiện, đừng mặc định mọi lớp của nhánh đó đã được đưa vào archive.

### 3.5. Chạy với archive và lưu log nguồn lớp

```powershell
java -Xshare:on '-XX:SharedArchiveFile=app.jsa' '-Xlog:class+load=info:file=classload.log:none' -jar app.jar
```

Stdout ứng dụng vẫn là:

```text
app.init
hello=CDS
topics=3
```

Log JVM được chuyển riêng vào `classload.log`. Tham số `none` ở phần trang trí log bỏ tiền tố thời gian/mức log, giúp ví dụ dễ đọc.

Lọc đúng hai lớp của ứng dụng:

```powershell
Select-String -LiteralPath classload.log -Pattern '^demo\.(Main|Greeting) ' |
    ForEach-Object { $_.Line }
```

Hai dòng đã quan sát được:

```text
demo.Main source: shared objects file (top)
demo.Greeting source: shared objects file (top)
```

`shared objects file` là bằng chứng lớp được nạp từ archive. Trong lượt này, hậu tố `(top)` chỉ phần archive động phía trên archive nền. Cách trình bày chi tiết có thể khác theo JDK.

Đây là kiểm tra trực tiếp hơn việc chỉ xác nhận tệp `app.jsa` tồn tại. Tệp tồn tại chưa chứng minh lần chạy sau thật sự sử dụng lớp trong tệp.

### 3.6. Dùng chế độ tự động khi vận hành

Lệnh kiểm tra ở trên dùng `-Xshare:on` để phát hiện rõ archive không dùng được. Với trường hợp cần cho phép JVM tiếp tục khi chia sẻ không thể kích hoạt, dùng chế độ tự động:

```powershell
java -Xshare:auto '-XX:SharedArchiveFile=app.jsa' -jar app.jar
```

Lệnh này cũng đã chạy đối chứng với cùng stdout trên môi trường kiểm chứng.

Lớp không nằm trong archive vẫn có thể được nạp theo đường thông thường. `-Xshare:on` không có nghĩa mọi lớp mà ứng dụng dùng đều bắt buộc đã được archive.

## 4. Ý nghĩa của ba chế độ Xshare

| Tùy chọn | Hành vi |
| --- | --- |
| `-Xshare:off` | Tắt CDS cho lần chạy |
| `-Xshare:auto` | Dùng CDS khi có thể, cho phép tiếp tục nếu không bật được |
| `-Xshare:on` | Yêu cầu bật được CDS; lỗi khởi động nếu không đáp ứng |

Tài liệu JVM dành `-Xshare:on` cho kiểm tra/chẩn đoán và không khuyến nghị dùng trong môi trường vận hành vì các thay đổi môi trường có thể khiến khởi động thất bại. Xem [điều khiển CDS thủ công](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html#manually-controlling-class-data-sharing).

Nếu đang chẩn đoán trường hợp tự động quay về cách nạp thường, có thể bật thêm log CDS:

```powershell
java -Xshare:auto '-XX:SharedArchiveFile=app.jsa' '-Xlog:cds=info' -jar app.jar
```

Đọc thông báo archive được chấp nhận hay bị từ chối; đừng dùng việc ứng dụng chạy thành công làm bằng chứng duy nhất cho CDS.

## 5. Vì sao app.init vẫn chạy?

Kết quả thí nghiệm có hai bằng chứng đồng thời:

1. Log cho thấy lớp `demo.Main` đến từ archive.
2. Mỗi JVM mới vẫn in `app.init`.

Như vậy, dùng dữ liệu lớp được chuẩn bị không có nghĩa khôi phục ứng dụng ngay sau khi `main` đã chạy. Logic khởi tạo ứng dụng vẫn có trách nhiệm của nó.

Tương tự, CDS không tự bỏ qua việc đọc cấu hình, mở kết nối cơ sở dữ liệu, xây dựng bộ nhớ đệm hoặc xử lý nghiệp vụ. Nếu phần khởi động chậm chủ yếu là chờ dịch vụ bên ngoài, chỉ bật CDS có thể đem lại ít khác biệt ở mốc sẵn sàng phục vụ.

JDK mới còn có cơ chế AOT cache rộng hơn, liên quan đến việc chuẩn bị trước dữ liệu phục vụ khởi động. Bài này giữ phạm vi ở CDS và archive động đã thực hành; không đồng nhất chúng với một tệp thực thi native hoặc bộ nhớ đệm mã máy JIT. Xem [phần Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#ahead-of-time-cache).

## 6. Archive là sản phẩm gắn với môi trường chạy

Một quy trình dễ kiểm soát:

```text
Chốt JDK và các JAR
        |
        v
Chạy tình huống đại diện để tạo archive
        |
        v
Kiểm tra log thực sự dùng archive
        |
        v
Phân phối cùng đúng ứng dụng và môi trường tương thích
```

Các điều kiện cần chú ý:

- **JDK:** archive phụ thuộc bản dựng JDK; bytecode `--release 17` không làm archive được tạo bởi JDK 24 trở thành archive dùng cho mọi JDK 17+.
- **JAR:** khi thay JAR sau lúc tạo archive, cần tạo lại archive phù hợp.
- **Classpath:** giữ đường nạp và thứ tự JAR nhất quán với lúc chuẩn bị.
- **Tùy chọn JVM/module:** những tùy chọn ảnh hưởng tương thích có thể làm archive bị từ chối hoặc chỉ dùng được một phần.
- **Archive nền:** archive động cần tương thích với phần nền được dùng để tạo nó.

Tài liệu lệnh `java` mô tả chi tiết [giới hạn classpath, module path và tính tương thích](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#restrictions-on-class-path-and-module-path). Thực hành an toàn về tính đúng đắn là tạo archive trong chuỗi dựng của chính bộ ứng dụng/JDK sẽ được chạy, rồi kiểm chứng tại môi trường đích.

Không thay archive cho việc phân phối JAR gốc. Archive là dữ liệu tối ưu hóa đi kèm; ứng dụng vẫn cần bộ lớp và tài nguyên theo hợp đồng chạy của nó.

## 7. Đánh giá hiệu quả đúng mục tiêu

Ví dụ đã chứng minh **đường nạp từ archive**, chưa chứng minh ứng dụng của bạn nhanh hơn một tỷ lệ cụ thể.

Khi đánh giá thực tế, cần:

| Mục tiêu | Cách giữ phép so sánh có ý nghĩa |
| --- | --- |
| Thời gian khởi động | Đo từ khởi chạy tiến trình đến cùng một mốc, chẳng hạn sẵn sàng phục vụ |
| Chi phí bộ nhớ | Phân biệt bộ nhớ riêng với trang chia sẻ, xem cả nhiều tiến trình |
| Độ bao phủ archive | Chạy tình huống đại diện, đọc log các lớp quan trọng |
| Độ ổn định | Lặp nhiều lần, giữ cùng JDK, JAR, cấu hình và điều kiện máy |

Không chỉ đặt `System.nanoTime()` ở đầu và cuối `main` rồi gọi đó là toàn bộ thời gian khởi động JVM: công việc trước khi vào `main` sẽ bị bỏ sót.

Bộ nhớ ánh xạ dùng chung cũng có thể xuất hiện trong thống kê của từng tiến trình. Cộng các số bộ nhớ tiến trình một cách máy móc có thể đếm lặp các trang chia sẻ; vì vậy, không suy ra lợi ích hay thiệt hại hệ thống chỉ từ một con số của một JVM.

CDS tập trung vào chi phí dữ liệu lớp và khởi động. Đừng dùng một kết quả khởi động tốt hơn để tự kết luận tốc độ xử lý nghiệp vụ ổn định hoặc độ trễ của mọi yêu cầu đều cải thiện.

## 8. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Việc kiểm tra |
| --- | --- |
| Không tạo được `app.jsa` | JVM có hỗ trợ không, đường ghi hợp lệ không, lượt chuẩn bị có kết thúc bình thường không |
| Archive có nhưng lớp ứng dụng vẫn nạp từ JAR | Lớp đó có được nạp khi chuẩn bị không; archive có được chấp nhận không |
| Đổi JDK rồi không dùng được archive | Tạo lại bằng đúng JDK đích |
| Đóng gói lại JAR rồi chế độ `on` báo lỗi | Archive được tạo từ bộ JAR cũ |
| Chỉ thấy lớp nền tảng dùng chia sẻ | Chưa chứng minh được AppCDS cho lớp ứng dụng |
| Thấy stdout giống hệt nên cho rằng CDS không hoạt động | CDS tối ưu cách chuẩn bị/nạp dữ liệu; hành vi ứng dụng đúng vẫn phải được giữ |

## 9. Tự thực hành

- Chạy lại lệnh có archive ở hai JVM mới: quan sát `app.init` và nguồn nạp của `Main`.
- Thêm một lớp chỉ nạp ở nhánh điều kiện, tạo archive khi nhánh chưa chạy rồi so sánh nguồn nạp khi bật nhánh.
- Sau khi đổi ứng dụng, tạo một archive mới thay vì tái sử dụng archive cũ.
- Nêu hai bằng chứng khác nhau: “tệp archive đã được tạo” và “lớp ứng dụng đã được nạp từ archive”.

Điểm cần giữ là quan hệ **lớp đã chuẩn bị → archive tương thích → dữ liệu lớp được dùng lại**. CDS giúp tránh lặp một phần công việc, trong khi mỗi JVM vẫn thực thi ứng dụng với trạng thái riêng của mình.
