# CDS: lợi ích và giới hạn đối với khởi động và bộ nhớ

## 1. CDS chia sẻ dữ liệu gì?

**Class Data Sharing (CDS)** là cơ chế của JVM, trong bài này xét Java HotSpot, cho phép chuẩn bị một phần dữ liệu liên quan tới lớp vào một tệp lưu trữ dùng lại, gọi là **archive**.

Khi JVM khởi động với archive phù hợp, nó có thể ánh xạ dữ liệu đó vào bộ nhớ thay vì lặp lại toàn bộ công việc đọc và phân tích các class file tương ứng.

Mô hình cơ bản:

```text
Không dùng dữ liệu đã lưu:
    JAR/runtime image → đọc và phân tích dữ liệu lớp → cấu trúc JVM cần dùng

Có archive phù hợp:
    archive → ánh xạ và dùng lại dữ liệu đã chuẩn bị
```

Các trang dữ liệu chỉ đọc phù hợp có thể được hệ điều hành chia sẻ giữa nhiều tiến trình JVM trên cùng máy chủ. Mỗi JVM vẫn là một tiến trình độc lập, có trạng thái thực thi của riêng nó.

Các thuật ngữ cần phân biệt:

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| CDS archive | Tệp chứa dữ liệu được JVM chuẩn bị để dùng lại |
| Archive mặc định | Archive lớp nền tảng do nhiều bản phân phối JDK cung cấp sẵn |
| AppCDS | Mở rộng phạm vi lưu trữ tới những lớp của ứng dụng/thư viện phù hợp |
| Static archive | Archive được tạo theo quy trình dựng archive riêng |
| Dynamic archive | Archive được tạo dựa trên các lớp được dùng trong một lần chạy, bổ sung trên một archive nền |

Đây là kỹ thuật tối ưu một phần công việc của JVM, không phải một bộ nạp toàn bộ ứng dụng vào RAM dùng chung cho mọi tiến trình.

Các cách làm dưới đây vẫn được tài liệu JDK hiện đại mô tả. Ví dụ dùng JDK 17+ có HotSpot/CDS; không giả định mọi JVM của mọi nhà cung cấp có cùng tùy chọn dòng lệnh.

## 2. Lợi ích đối với thời gian khởi động

### Giảm công việc lặp lại về dữ liệu lớp

Nhiều ứng dụng cùng dùng các lớp nền tảng và thư viện tương tự. Nếu mỗi tiến trình đều đọc, giải mã và tạo lại dữ liệu lớp từ đầu, công việc đó bị lặp lại.

CDS chuẩn bị một phần dữ liệu ở dạng JVM dùng nhanh hơn. Khi archive phù hợp, JVM có thể giảm công việc xử lý lớp ở những lần khởi động sau.

Điểm quan trọng là **phần việc nào được giảm**, không phải chỉ việc có thêm một tệp `.jsa`. Một archive không được JVM sử dụng sẽ không đem lại lợi ích dự kiến cho các lớp chứa trong nó.

### Lợi ích có thể rõ hơn với ứng dụng sống ngắn

Nếu ứng dụng chủ yếu khởi động, nạp một nhóm lớp rồi xử lý ít công việc trước khi kết thúc, việc giảm thời gian chuẩn bị lớp có thể chiếm tỷ lệ đáng kể trong tổng thời gian chạy.

Một dịch vụ sống lâu vẫn có thể hưởng lợi khi triển khai, khởi tạo thêm bản sao hoặc khôi phục sau khi dừng. Tuy nhiên, giảm khởi động không tự suy ra thông lượng nghiệp vụ trong nhiều giờ sau đó cũng tăng cùng tỷ lệ.

### AppCDS mở rộng phần việc được chuẩn bị

Archive mặc định thường tập trung vào các lớp thuộc JDK. Ứng dụng thực tế còn nạp nhiều lớp từ chính ứng dụng và thư viện.

AppCDS giúp những lớp đủ điều kiện trong phần đó cũng được đưa vào archive. Do đó, cần phân biệt:

```text
Chia sẻ lớp nền tảng
    ≠
đã chia sẻ được mọi lớp ứng dụng
```

Chạy JVM với chế độ mặc định có thể đã dùng archive nền tảng. Nếu muốn biết AppCDS bổ sung được gì, đường cơ sở nên tính đến thực tế đó, thay vì luôn so “tắt toàn bộ CDS” với “bật cả archive ứng dụng” rồi quy toàn bộ lợi ích cho riêng AppCDS.

## 3. Lợi ích đối với bộ nhớ

### Các phần chỉ đọc có thể dùng chung

Khi nhiều JVM cùng sử dụng một archive tương thích, một phần trang chỉ đọc được ánh xạ từ tệp có thể dùng chung ở cấp hệ điều hành.

Có thể hình dung:

```text
JVM A ─┐
       ├─> các trang dữ liệu chỉ đọc dùng chung từ archive
JVM B ─┘

JVM A vẫn có heap, luồng và trạng thái riêng.
JVM B vẫn có heap, luồng và trạng thái riêng.
```

Lợi ích này đáng quan tâm khi có nhiều JVM trên cùng máy và chúng dùng dữ liệu lớp trùng nhau.

Không được cộng kích thước toàn bộ archive vào mỗi tiến trình rồi coi tất cả là bộ nhớ vật lý riêng. Ngược lại, cũng không được xem toàn bộ vùng đã ánh xạ đều là phần chia sẻ chỉ đọc.

### Mỗi JVM vẫn cần bộ nhớ riêng

CDS không làm những thành phần sau tự trở thành một vùng dùng chung cho mọi ứng dụng:

- Các đối tượng nghiệp vụ có thể thay đổi.
- Cache dữ liệu và phiên làm việc của ứng dụng.
- Ngăn xếp các luồng.
- Trạng thái tĩnh có thể thay đổi.
- Kết nối, bộ đệm và tài nguyên của từng tiến trình.
- Toàn bộ mã máy JIT và mọi thông tin thực thi đang có.

Một số dạng archive/triển khai có thể lưu các đối tượng heap được chọn để hỗ trợ JVM. Điều đó không có nghĩa CDS lưu rồi chia sẻ tùy ý toàn bộ heap nghiệp vụ hoặc toàn bộ trạng thái của một dịch vụ đang chạy.

Vì vậy, bật CDS không tự làm giảm lượng dữ liệu ứng dụng phải giữ. Nếu bộ nhớ chủ yếu nằm ở một cache hàng gigabyte, tối ưu dữ liệu lớp có thể chỉ tác động một phần nhỏ tổng footprint.

### Xmx không phải tổng bộ nhớ của tiến trình

`-Xmx` giới hạn kích thước tối đa của Java heap; nó không phải phép đo tổng bộ nhớ của JVM. CDS có liên quan dữ liệu lớp và các ánh xạ bộ nhớ, nên chỉ nhìn heap không đủ đánh giá tác động.

Cũng không được nhìn thấy tệp archive lớn rồi kết luận tiến trình phải giữ riêng toàn bộ số byte đó trong RAM. Tệp trên đĩa, không gian địa chỉ đã ánh xạ và các trang thực sự cư trú là ba đại lượng khác nhau.

## 4. Những giới hạn quan trọng

### 4.1. CDS không xóa mọi công việc khởi động

Ứng dụng vẫn có thể cần:

- Chạy mã khởi tạo tĩnh và constructor.
- Đọc cấu hình và tài nguyên.
- Tạo đồ thị đối tượng của framework.
- Quét thông tin ứng dụng theo cơ chế framework sử dụng.
- Mở kết nối cơ sở dữ liệu hoặc dịch vụ ngoài.
- Thực hiện xác thực, nạp dữ liệu và kiểm tra sẵn sàng.

Nếu thời gian khởi động chủ yếu chờ một dịch vụ ngoài, giảm xử lý dữ liệu lớp sẽ không loại bỏ thời gian chờ đó.

Có thể dùng cách phân tích gần đúng:

```text
Thời gian khởi động
    = phần công việc về lớp mà CDS có thể hỗ trợ
      + phần công việc khác
```

Đây chỉ là mô hình để phân tích, không phải bảo đảm các phần luôn tách biệt hoàn toàn khi đo thực tế.

### 4.2. Archive cần phù hợp với môi trường và ứng dụng

Archive gắn với cách JVM biểu diễn dữ liệu nội bộ. Không coi nó như một JAR Java có thể dùng ở mọi phiên bản nền tảng.

Cần tạo và dùng archive với cấu hình tương thích, đặc biệt:

- Đúng bản JDK/build được dùng để tạo dữ liệu.
- Đúng hệ điều hành và kiến trúc phù hợp.
- Các JAR, classpath/module path và tùy chọn liên quan phù hợp.
- Archive nền cần thiết vẫn có thể được dùng.

Khi đổi JDK hoặc cập nhật ứng dụng/thư viện, cần đánh giá và thường tạo lại archive. Một pipeline đáng tin cậy nên gắn archive với đúng artifact và runtime, thay vì sao chép một tệp cũ chỉ vì tên ứng dụng giống nhau.

### 4.3. Không phải lớp nào cũng được lưu hoặc dùng từ archive

Dynamic archive phản ánh những lớp đủ điều kiện đã được dùng trong lần chạy chuẩn bị. Nhánh chức năng không được chạy có thể cần nạp thêm lớp bình thường về sau.

Điều đó không có nghĩa chương trình sai; nó có thể chỉ không có lợi ích CDS cho phần lớp chưa được chuẩn bị. Cần chọn lần chạy đại diện cho mục tiêu: khởi động đến trạng thái sẵn sàng hay một số luồng xử lý quan trọng.

CDS hiện đại không chỉ dành cho lớp bootstrap. Tuy nhiên, khả năng với bộ nạp tùy biến, lớp sinh động, module và các tùy chọn cụ thể cần đối chiếu đúng bản JDK. Không suy từ “AppCDS có hỗ trợ bộ nạp tùy biến” thành “mọi lớp động trong mọi framework đều được lưu và tái sử dụng”.

### 4.4. Classpath và đóng gói có ràng buộc

Quy trình trong bài dùng JAR thay vì thư mục lớp đã biên dịch. Tài liệu CDS đặt các ràng buộc cụ thể lên classpath/module path khi tạo và dùng archive, trong đó có thư mục không rỗng và sự thay đổi của các JAR.

Theo tài liệu lệnh Java được đối chiếu, classpath khi tạo archive phải giống hoặc là phần đầu của classpath khi dùng; sửa các JAR liên quan sau khi tạo có thể làm archive không dùng được.

Cách làm đơn giản để tránh sai lệch là dùng cùng các JAR ổn định, cùng thứ tự và cách khởi chạy khi tạo lẫn khi dùng, rồi xác minh bằng log.

Không tùy ý giải nén/đóng lại JAR, đổi dependency hoặc thay đường khởi chạy và giả định archive vẫn có hiệu lực. Framework có cách đóng gói riêng cần theo quy trình được framework/JDK hỗ trợ.

### 4.5. Agent và biến đổi lớp có thể ảnh hưởng khả năng chia sẻ

Một agent biến đổi lớp có thể làm quá trình sử dụng dữ liệu đã lưu khác với cấu hình không có agent. Tùy cơ chế và phiên bản JDK, một số tối ưu hoặc lớp được chia sẻ có thể không được sử dụng như dự kiến.

Không kết luận rằng “có agent thì CDS luôn tắt” hoặc “archive được tạo không có agent chắc chắn có cùng hiệu quả khi thêm mọi agent”. Cần kiểm tra đúng tổ hợp triển khai và đọc log.

### 4.6. Tạo archive cũng có chi phí

Lần chạy chuẩn bị tiêu tốn thời gian và tài nguyên. Archive cần dung lượng lưu trữ và quy trình phát hành cùng ứng dụng.

Dữ liệu lớp trong archive được lưu theo định dạng thuận tiện cho JVM, không nhất thiết nhỏ hơn các class file đã nén trong JAR. Chỉ lưu những phần có ích và đo lợi ích sau đó sẽ hợp lý hơn việc cố tạo archive chứa mọi thứ có thể chứa.

Tạo archive rồi chỉ dùng đúng một lần có thể không mang lại lợi ích tổng thể bằng tái sử dụng nó trong nhiều lần khởi động. Cần xác định phạm vi tính chi phí: thời gian build, thời gian khởi động phục vụ người dùng hay tổng vòng đời.

### 4.7. CDS không phải lưu mã máy JIT của mọi phương thức

CDS theo quy trình truyền thống của bài chủ yếu chuẩn bị dữ liệu lớp, không lưu nguyên mọi tối ưu JIT mà một tiến trình trước đã học được.

Các JDK mới có cơ chế AOT cache xây dựng trên nền tảng này để tiến xa hơn trong chuẩn bị trước công việc. **AOT cache không đồng nghĩa bản thực thi native độc lập**, và các khả năng/điều kiện của nó phải đọc theo đúng phiên bản JDK.

Không lấy một mô tả CDS cũ rồi dùng nó để kết luận mọi dạng cache AOT hiện đại chỉ có đúng cùng tập dữ liệu hoặc cùng mức lợi ích. Phần thực hành dưới đây giới hạn ở CDS/AppCDS còn được tài liệu Java hiện đại mô tả.

## 5. Thí nghiệm: chứng minh lớp được lấy từ archive

Mục tiêu là xác minh cơ chế hoạt động, không công bố một tỷ lệ tăng tốc hay giảm bộ nhớ từ chương trình quá nhỏ.

### 5.1. Mã nguồn

Tệp `src/demo/Hello.java`:

```java
package demo;

import java.util.List;

public final class Hello {
    static {
        System.out.println("init=executed");
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(1, 2, 3);
        int sum = 0;
        for (int value : values) {
            sum += value;
        }
        System.out.println("items=" + values.size() + " sum=" + sum);
    }
}
```

Dòng `init=executed` được đặt trong khối khởi tạo tĩnh để kiểm tra rằng dùng CDS không đồng nghĩa bỏ qua mã khởi tạo ứng dụng.

Từ thư mục chứa `src`, dùng JDK 17+ có CDS và chạy trong PowerShell:

```powershell
javac --release 17 -d classes src/demo/Hello.java
jar --create --file cds-demo.jar --main-class demo.Hello -C classes .
```

Chỉ tiếp tục nếu từng lệnh thành công.

Thư mục `classes` chỉ phục vụ biên dịch/đóng gói. Các lệnh tạo và dùng archive sẽ chạy trên `cds-demo.jar`.

### 5.2. Tạo dynamic archive

```powershell
java "-XX:ArchiveClassesAtExit=app.jsa" "-Xlog:cds=info:file=training-cds.log" -cp cds-demo.jar demo.Hello
```

Stdout của ứng dụng:

```text
init=executed
items=3 sum=6
```

Khi JVM kết thúc bình thường, nó tạo `app.jsa` từ các lớp đủ điều kiện trong lần chạy, bổ sung cho archive nền. Lệnh của bài giả định bản JDK có archive nền dùng được.

Kiểm tra tệp được tạo và xem log thay vì chỉ tin vào stdout. Trong PowerShell:

```powershell
Get-Item -LiteralPath app.jsa
Get-Content -LiteralPath training-cds.log
```

Kích thước tệp và chi tiết log phụ thuộc JDK, môi trường và các lớp đã nạp, nên bài không đưa một kích thước bắt buộc.

Lần chạy tạo archive không phải lần đo khởi động có archive đã sẵn sàng: nó còn thực hiện công việc tạo tệp.

### 5.3. Bắt buộc dùng archive để kiểm chứng

```powershell
java -Xshare:on "-XX:SharedArchiveFile=app.jsa" "-Xlog:class+load=info:file=with-cds-load.log" -cp cds-demo.jar demo.Hello
```

Stdout vẫn là:

```text
init=executed
items=3 sum=6
```

`-Xshare:on` trong bước này là tùy chọn **kiểm chứng**: JVM phải dùng được CDS hoặc báo lỗi và dừng. Nó giúp tránh trường hợp chạy thành công nhưng âm thầm không dùng chia sẻ.

Tài liệu JDK khuyến cáo không dùng chế độ bắt buộc này như lựa chọn production mặc định, vì archive không tương thích có thể làm JVM không khởi động. Khi vận hành cần lựa chọn chế độ và chính sách fallback phù hợp, đồng thời quan sát archive có thực sự được dùng.

Tìm lớp ứng dụng trong log:

```powershell
Select-String -LiteralPath with-cds-load.log -SimpleMatch "demo.Hello source:" | ForEach-Object { $_.Line }
```

Trong lần kiểm tra bằng JDK 24.0.2, phần quan trọng của dòng log là:

```text
demo.Hello source: shared objects file (top)
```

Đây là trích phần nội dung cần nhận diện, không phải toàn bộ dòng log: dấu thời gian, cách trang trí và một số chi tiết có thể khác theo JDK.

Dấu `(top)` trong cấu hình này cho biết lớp đến từ archive dynamic phía trên archive nền.

### 5.4. Tắt CDS để đối chiếu nguồn lớp

```powershell
java -Xshare:off "-Xlog:class+load=info:file=without-cds-load.log" -cp cds-demo.jar demo.Hello
```

Stdout:

```text
init=executed
items=3 sum=6
```

Kiểm tra log:

```powershell
Select-String -LiteralPath without-cds-load.log -SimpleMatch "demo.Hello source:" | ForEach-Object { $_.Line }
```

Nguồn lớp lúc này là đường dẫn tới `cds-demo.jar`, thay vì `shared objects file`. Đường dẫn tuyệt đối phụ thuộc nơi đặt thư mục thực hành.

### 5.5. Những điều được và chưa được chứng minh

Ví dụ đã được biên dịch với `--release 17` và chạy kiểm tra trên JDK 24.0.2.

Nó chứng minh:

- Archive ứng dụng được tạo và dùng lại.
- Lớp `demo.Hello` được lấy từ archive khi cấu hình phù hợp.
- Tắt CDS khiến lớp được nạp từ JAR.
- Bộ khởi tạo tĩnh vẫn chạy trong mỗi tiến trình.
- Kết quả ứng dụng không đổi giữa các chế độ.

Nó chưa chứng minh:

- Tăng tốc một tỷ lệ cố định.
- Mỗi tiến trình giảm một lượng RAM cố định.
- Mọi lớp của một hệ thống lớn đều được chia sẻ.
- Mọi trạng thái ứng dụng được khôi phục từ archive.

Chỉ nhìn dấu thời gian của hai dòng nạp lớp riêng lẻ cũng không đủ để đo thời gian khởi động toàn bộ.

## 6. Hiểu các chế độ Xshare

| Tùy chọn | Ý nghĩa thực dụng |
| --- | --- |
| `-Xshare:off` | Tắt CDS để chẩn đoán/đối chiếu |
| `-Xshare:on` | Yêu cầu CDS dùng được; lỗi nếu không thể, thích hợp kiểm chứng |
| `-Xshare:auto` | Cho phép dùng CDS khi có thể; là lựa chọn thông thường của cơ chế CDS trên HotSpot hiện đại |

`auto` không phải lời hứa tự sửa mọi lỗi cấu hình hoặc mọi lỗi ứng dụng. Hãy đọc log để biết archive nào và những lớp nào đã được dùng.

Nhiều bản phân phối JDK hiện đại đã cung cấp và bật archive mặc định. Do đó, lệnh `java` không ghi rõ `-Xshare` không có nghĩa chắc chắn CDS đang tắt. Tài liệu Oracle JDK mô tả archive mặc định được đóng gói từ JDK 12.

Không cần thêm một cờ riêng để “mở khóa thương mại” AppCDS theo các hướng dẫn rất cũ. Với bài này, sử dụng các tùy chọn còn được tài liệu JDK hiện đại nêu rõ.

## 7. Đo lợi ích khởi động đúng cách

### Xác định mốc bắt đầu và kết thúc

Với công cụ dòng lệnh, có thể quan tâm từ lúc tạo tiến trình đến khi công việc hoàn tất. Với dịch vụ, có thể quan tâm từ lúc khởi chạy đến khi endpoint sẵn sàng phục vụ theo điều kiện đã định nghĩa.

Chỉ đo khoảng trong `main` sẽ bỏ phần khởi động JVM trước đó. Chỉ đo “cổng TCP đã mở” cũng có thể sớm hơn lúc dịch vụ thực sự dùng được.

### Tách ba cấu hình khi cần hiểu AppCDS

```text
A: tắt CDS hoàn toàn
B: cấu hình thông thường, dùng archive JDK nếu có
C: thêm archive ứng dụng phù hợp
```

A so với B giúp hiểu phần mặc định. B so với C giúp hiểu phần bổ sung của archive ứng dụng. Phải xác minh bằng log rằng từng cấu hình thật sự có hiệu lực.

### Giữ điều kiện tương đương

Dùng cùng JDK/build, artifact ứng dụng, cấu hình, tài nguyên và luồng công việc. Tạo archive trước khi đo các lần tái sử dụng.

Chạy nhiều lần độc lập và xem phân bố. Hệ điều hành có cache tệp, nên lần chạy đầu và các lần chạy sau có thể khác nhau ngay cả khi không dùng CDS. Không so một lần chạy nguội của A với một lần chạy sau đã có cache của C rồi quy toàn bộ khác biệt cho CDS.

Không bật log nạp mọi lớp trong phép đo chính nếu cấu hình còn lại không bật cùng mức log. Log hữu ích để xác minh, nhưng I/O log có thể làm nhiễu thời gian.

### Không cam kết phần trăm từ ví dụ nhỏ

Nếu phần khởi động chủ yếu là lớp, CDS có cơ hội tác động nhiều hơn. Nếu chủ yếu là mở kết nối và nạp dữ liệu ngoài, mức tăng tốc tổng thể có thể nhỏ hơn.

Một ứng dụng lớn có thể có nhiều lớp nhưng cũng nhiều công việc không liên quan CDS. Kích thước JAR hoặc số lượng dependency đơn lẻ không dự báo đầy đủ lợi ích.

## 8. Đo lợi ích bộ nhớ đúng cách

### Một tiến trình và nhiều tiến trình là hai câu hỏi khác nhau

Với một JVM, có thể quan tâm footprint của chính tiến trình. Với nhiều JVM, cần quan tâm tổng bộ nhớ vật lý và phần dùng chung giữa chúng.

Một phần lợi ích chia sẻ rõ hơn khi nhiều JVM dùng cùng dữ liệu archive trên cùng host. “Nhiều container có tệp cùng tên” chưa tự chứng minh chúng đang dùng chung đúng các trang vật lý; cần đo trong cách triển khai thực tế.

### Không cộng RSS rồi coi đó là tổng duy nhất

Trên Linux, RSS của từng tiến trình có thể gồm các trang được chia sẻ. Cộng RSS của nhiều JVM có thể tính cùng một trang nhiều lần.

PSS phân bổ một trang dùng chung theo tỷ lệ giữa các tiến trình ánh xạ nó; đó là một góc nhìn hữu ích khi đánh giá tổng footprint. Tài liệu kernel mô tả dữ liệu theo ánh xạ trong `/proc/<pid>/smaps` và bản tổng hợp `smaps_rollup`.

Không chuyển tên/chỉ số đo của Linux thành giả định cho Windows. Trên từng hệ điều hành, cần phân biệt bộ nhớ riêng, phần cư trú và các ánh xạ có thể chia sẻ bằng công cụ phù hợp.

### Đo cùng trạng thái ứng dụng

So sánh tại cùng mức sẵn sàng hoặc cùng tải, cùng heap và số luồng hợp lý. Nếu cấu hình A vừa khởi động còn C đã xử lý thêm dữ liệu, khác biệt footprint có thể đến từ công việc khác nhau.

Quan sát cả vùng dùng chung và vùng riêng. Bộ nhớ địa chỉ được dự trữ, kích thước archive trên đĩa và bộ nhớ vật lý đang dùng không phải một số duy nhất.

Ví dụ `Hello` kết thúc rất nhanh nên không phù hợp để rút ra kết luận đáng tin cậy về footprint của một dịch vụ nhiều tiến trình. Hãy dùng một kịch bản có vòng đời đủ lâu và tải đại diện cho mục tiêu đo.

## 9. Khi nào nên kỳ vọng lợi ích và khi nào cần điều tra thêm?

| Tình huống | Cách suy nghĩ |
| --- | --- |
| Nhiều JVM tương tự trên cùng host | Có cơ hội chia sẻ dữ liệu lớp; cần đo tổng bộ nhớ và phần dùng chung |
| Công cụ sống ngắn, nạp nhiều lớp so với công việc thực hiện | Giảm công việc lớp có thể tác động rõ tới tổng thời gian |
| Dịch vụ cần khởi tạo thêm bản sao nhanh | Đo đến trạng thái sẵn sàng, không chỉ đến `main` |
| Khởi động chủ yếu chờ cơ sở dữ liệu | CDS không loại bỏ thời gian chờ đó |
| Heap bị chi phối bởi dữ liệu nghiệp vụ | Đừng kỳ vọng CDS xử lý nguyên nhân tiêu thụ heap |
| JDK/dependency thay đổi thường xuyên | Cần quy trình tạo lại và kiểm chứng archive |
| Chạy thành công nhưng không thấy nhanh hơn | Xác minh archive được dùng, phạm vi lớp, nhiễu đo và phần việc còn lại |
| Có agent hoặc bộ nạp riêng | Kiểm tra đúng tổ hợp, không dùng giả định từ chương trình classpath đơn giản |

CDS thường là một lớp tối ưu trong nhiều lớp tối ưu. Nó không thay thế việc tìm điểm nghẽn, quản lý dữ liệu ứng dụng hoặc chọn đúng mốc đo.

## 10. Bài tập tự kiểm chứng

1. Đổi dòng in trong `Hello`, đóng gói lại JAR rồi thử dùng archive cũ trong chế độ kiểm chứng. Đọc log/lỗi của đúng JDK đang dùng; giải thích vì sao cập nhật artifact phải đi cùng đánh giá archive.
2. Bỏ `-XX:SharedArchiveFile=app.jsa` nhưng không dùng `-Xshare:off`. Kiểm tra một lớp JDK trong log để xem cấu hình mặc định có đang dùng archive nền hay không.
3. Giải thích vì sao `init=executed` vẫn được in khi `demo.Hello` lấy từ archive. Phân biệt dữ liệu lớp đã chuẩn bị với trạng thái tĩnh nghiệp vụ của một tiến trình cũ.
4. Nếu độ trễ sẵn sàng không giảm dù lớp ứng dụng đã dùng archive, liệt kê các việc khởi động còn lại cần đo.
5. Nếu tổng RSS của bốn JVM không giảm như kỳ vọng, vì sao chưa thể kết luận không có trang nào được chia sẻ? Cần thêm chỉ số nào trên hệ điều hành đang dùng?
6. Thiết kế phép so B và C để đo phần lợi ích riêng của AppCDS, tránh trộn nó với lợi ích archive JDK mặc định.

Điều cần nắm là **CDS giảm một phần công việc về lớp và cho phép chia sẻ một phần dữ liệu phù hợp; lợi ích khởi động và bộ nhớ phụ thuộc archive thực sự được dùng, mức trùng dữ liệu và phần việc còn lại của ứng dụng**.

## Tài liệu đối chiếu

- [Class Data Sharing — Oracle JDK 25](https://docs.oracle.com/en/java/javase/25/vm/class-data-sharing.html): mục tiêu, ánh xạ chia sẻ và chế độ sử dụng.
- [Lệnh java — Application Class Data Sharing, JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html#application-class-data-sharing): tạo/dùng archive và ràng buộc classpath.
- [Lệnh java — Ahead-of-Time Cache, JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html#ahead-of-time-cache): phân biệt cơ chế cache hiện đại mở rộng từ CDS.
- [Linux kernel — /proc filesystem](https://docs.kernel.org/filesystems/proc.html): cách hiểu RSS, PSS và thông tin ánh xạ bộ nhớ.
