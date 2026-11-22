# Tạo kho AppCDS tĩnh bằng `-Xshare:dump` (Java 10+)

## 1. Vấn đề và mục tiêu bài học

Khi khởi động một ứng dụng Java, JVM phải tìm các lớp, đọc bytecode từ JAR/module, xác minh và tạo các cấu trúc nội bộ cần thiết trước khi những lớp đó được sử dụng. Với các ứng dụng có nhiều lớp hoặc với workload cần khởi động nhiều lần, một phần công việc này có thể được thực hiện **trước** và lưu vào một **CDS archive**.

**Application Class-Data Sharing (AppCDS)** mở rộng cơ chế Class Data Sharing (CDS) để lưu cả metadata lớp của ứng dụng và thư viện, không chỉ một tập lớp nền tảng của JDK. AppCDS xuất hiện trong **Java 10 qua JEP 310**, và quy trình tạo **kho tĩnh (static CDS archive)** bằng tùy chọn **`-Xshare:dump`** vẫn được tài liệu Java hiện hành mô tả.

Điều quan trọng: `-Xshare:dump` là **lệnh tạo archive**, không phải lệnh khởi chạy ứng dụng bằng archive. Để tạo một archive có chứa các lớp ứng dụng, ta thường phải:

1. **Biên dịch/đóng gói** chương trình thành JAR.
2. **Chạy thử** ứng dụng để ghi lại danh sách lớp đã nạp (`classlist`).
3. **Dump** các lớp trong danh sách vào một file archive tĩnh (`.jsa`) bằng `-Xshare:dump`.
4. **Khởi chạy** ứng dụng với `-XX:SharedArchiveFile=...`.
5. **Kiểm tra log lớp** để chứng minh lớp ứng dụng thật sự được nạp từ archive, không chỉ dựa vào việc file có tồn tại.

Mục tiêu là hiểu đúng cơ chế, biết tạo và xác minh archive, phát hiện khi nó không được dùng, xử lý các ràng buộc classpath/JDK, và biết khi nào quy trình tĩnh này nên được cân nhắc so với giải pháp AOT/cache hiện đại hơn.

**Lưu ý phiên bản:** Java 10 là mốc AppCDS quan trọng, nhưng bài sử dụng cách viết phù hợp JDK 17+ để có một ví dụ có thể chạy. Trong JDK 24+ đã có **AOT cache**, nên `-Xshare:dump` không phải lựa chọn duy nhất, cũng không nhất thiết là lựa chọn tốt nhất cho mọi ứng dụng mới. Không có lý do bắt buộc phải chạy một JDK 10 cũ đã hết hỗ trợ chỉ để sử dụng các cơ chế AppCDS vẫn tồn tại trên JDK mới.

## 2. CDS, AppCDS và file `.jsa` là gì?

### 2.1. Trước khi dùng CDS

Trong một lần chạy không tận dụng archive, JVM cần xử lý các bước liên quan tới lớp như đọc bytecode, xác minh và xây dựng cấu trúc runtime. Những bước này lặp lại giữa các lần khởi chạy của cùng một ứng dụng.

CDS giúp **lưu trước một số dữ liệu lớp đã qua xử lý** để JVM có thể ánh xạ hoặc nạp nhanh hơn ở những lần sau. Nó có thể hỗ trợ giảm thời gian startup, và tùy môi trường có thể có lợi về footprint/bộ nhớ chia sẻ.

**CDS không phải**:

- một cơ chế lưu database hoặc trạng thái nghiệp vụ giữa các lần chạy;
- một bản dump của Java heap ứng dụng đang sống;
- một file JAR mới chứa toàn bộ source/bytecode để phát hành thay JAR gốc;
- một bản biên dịch native hoàn chỉnh như executable của GraalVM Native Image;
- một bảo đảm tốc độ được tăng một tỷ lệ cố định trên mọi workload.

### 2.2. CDS mặc định và AppCDS của ứng dụng

Nhiều bản phân phối HotSpot hiện đại đã đi kèm một **default CDS archive**, thường có tên `classes.jsa`, chứa các lớp JDK phổ biến. Bật CDS mặc định **không tự động bảo đảm các lớp nghiệp vụ trong `hello.jar` đã nằm trong archive**.

AppCDS hướng tới một tập lớp của ứng dụng. Để archive thực sự chứa `demo.Hello`, cần danh sách lớp phù hợp và archive tương ứng; sau đó xác minh `demo.Hello` được load từ `shared objects file`.

### 2.3. Static archive khác dynamic archive

| Tiêu chí | Static archive bằng `-Xshare:dump` | Dynamic archive bằng `-XX:ArchiveClassesAtExit` |
| --- | --- | --- |
| Cách tạo | Có bước thu classlist rồi JVM dump tĩnh | JVM ghi thêm dữ liệu lớp khi ứng dụng kết thúc |
| Danh sách lớp | Truyền qua `-XX:SharedClassListFile` | Không cần classlist thủ công |
| Quan hệ với base archive | Static archive có thể dùng độc lập theo cấu hình phù hợp | Dynamic archive sử dụng một base static archive |
| Hỗ trợ trong JDK hiện đại | Vẫn được tài liệu Java 27 mô tả | Vẫn được hỗ trợ |
| Mức công sức vận hành | Chủ động kiểm soát danh sách lớp và giai đoạn dump | Thường đơn giản hơn khi không cần kiểm soát sâu |

**JDK 13** bổ sung cơ chế tạo dynamic CDS archives; **JDK 19** bổ sung `-XX:+AutoCreateSharedArchive` giúp tự động tạo/tái tạo archive trong một số điều kiện. Từ **JDK 24**, AOT cache có mô hình training/assembly/runtime riêng, và các JDK mới có thêm các tối ưu AOT. Vì thế, khi triển khai hệ thống mới trên JDK 25+, cần **đánh giá AOT cache** thay vì mặc nhiên áp dụng một bài hướng dẫn AppCDS cũ cho mọi trường hợp.

Tuy vậy, **static CDS dump bằng `-Xshare:dump` vẫn là cơ chế thực tế và còn áp dụng** khi bạn cần tạo một static archive có kiểm soát. Đó là phạm vi của bài học này.

## 3. Những tùy chọn JVM tham gia quy trình

### 3.1. `-Xshare:off`

```bash
java -Xshare:off -cp hello.jar demo.Hello
```

Tắt việc dùng CDS trong lần chạy này. Khi **ghi danh sách lớp đã nạp**, tài liệu JDK khuyên kết hợp `-Xshare:off` để quan sát các lớp thực sự được nạp trong workload.

Không dùng `-Xshare:off` cho production chỉ vì “đã có file archive”. Nếu tắt CDS thì mục tiêu tận dụng archive không được thực hiện.

### 3.2. `-XX:DumpLoadedClassList=hello.classlist`

```bash
java -Xshare:off -XX:DumpLoadedClassList=hello.classlist \
     -cp hello.jar demo.Hello
```

Đây là lệnh **chạy ứng dụng thật** và ghi vào file `hello.classlist` danh sách các lớp JVM đã nạp. Danh sách này thường chứa cả lớp nền tảng và lớp của ứng dụng.

**Lưu ý:** dấu `\` cuối dòng ở ví dụ là cú pháp nối dòng của shell POSIX. Trong PowerShell hoặc Windows CMD, hãy dùng một dòng:

```powershell
java -Xshare:off -XX:DumpLoadedClassList=hello.classlist -cp hello.jar demo.Hello
```

Chỉ những lớp được nạp trong **workload thu thập** mới có cơ hội nằm trong classlist. Nếu một nhánh code chỉ chạy khi có request/điều kiện đặc biệt, thử nghiệm khởi động đơn giản có thể bỏ sót các lớp của nhánh đó.

### 3.3. `-XX:SharedClassListFile=hello.classlist`

Tùy chọn này chỉ định **classlist đầu vào cho giai đoạn dump**. Trong trường hợp thông thường bạn không phải tự gõ tất cả tên lớp bằng tay: hãy dùng file mà `DumpLoadedClassList` vừa tạo, hoặc quy trình profiling đáng tin cậy có cùng định dạng.

Classlist không phải script để JVM thực thi. Nó mô tả những lớp có thể đưa vào archive, gồm tên nội bộ như `demo/Hello` và các thông tin bổ sung do JVM sinh ra khi cần.

### 3.4. `-Xshare:dump`

```bash
java -Xshare:dump \
     -XX:SharedClassListFile=hello.classlist \
     -XX:SharedArchiveFile=hello.jsa \
     -cp hello.jar
```

Đây là **giai đoạn tạo kho tĩnh**. JVM đọc classlist và các nguồn lớp phù hợp rồi ghi archive `hello.jsa`. Lệnh không chứa `demo.Hello` ở cuối bởi vì nó **không phải một lần gọi `main` của ứng dụng**.

Trong JDK hiện hành, `-Xshare:dump` mặc định chạy theo chế độ interpreter-only trong quá trình dump để hỗ trợ tính xác định của nội dung archive. Tài liệu `java` còn đề cập việc tùy chọn `-Xmixed` có thể rút ngắn thời gian dump classlist lớn nếu không cần cùng mức tính xác định. Đây là **tùy chọn tối ưu quá trình tạo**, không có nghĩa archive biến thành mã native JIT đã biên dịch.

### 3.5. `-XX:SharedArchiveFile=hello.jsa`

```bash
java -XX:SharedArchiveFile=hello.jsa \
     -cp hello.jar demo.Hello
```

Đây là lần chạy ứng dụng **có yêu cầu dùng archive**. JVM tìm và dùng các lớp phù hợp trong file `hello.jsa` theo quy tắc CDS.

**Hai vai trò khác nhau của cùng tùy chọn:**

- Trong **dump**, `-XX:SharedArchiveFile` là **đường dẫn file đầu ra**.
- Trong **runtime**, `-XX:SharedArchiveFile` là **đường dẫn archive cần nạp**.

Không lẫn ý nghĩa chỉ vì tên tùy chọn giống nhau.

### 3.6. `-Xshare:auto` và `-Xshare:on`

`-Xshare:auto` sử dụng CDS khi có thể; nếu archive không dùng được, JVM có thể chạy theo con đường bình thường. Đây là chế độ mặc định trên phần lớn HotSpot JDK hiện nay.

`-Xshare:on` yêu cầu CDS phải dùng được; nếu không, JVM **thoát với lỗi**. Tài liệu JDK khuyến cáo `-Xshare:on` chỉ phục vụ kiểm thử/chẩn đoán, **không dùng như tùy chọn production** vì archive bị lỗi hoặc không tương thích có thể khiến ứng dụng không khởi động.

```bash
# Tùy chọn chỉ dùng khi kiểm tra archive:
java -Xshare:on -XX:SharedArchiveFile=hello.jsa \
     -cp hello.jar demo.Hello
```

Với production, lựa chọn an toàn hơn là chế độ mặc định/`auto` cùng giám sát hiệu năng và log phù hợp. Việc **yêu cầu** archive bằng `on` khác với **xác minh archive được sử dụng** qua log: ưu tiên xác minh độc lập thay vì biến tối ưu thành điều kiện sống còn của service.

## 4. Sơ đồ thao tác đầy đủ

```text
src/demo/Hello.java
       |
       | javac, jar
       v
    hello.jar
       |
       | java -Xshare:off
       | -XX:DumpLoadedClassList=hello.classlist
       v
 hello.classlist
       |
       | java -Xshare:dump
       | -XX:SharedClassListFile=hello.classlist
       | -XX:SharedArchiveFile=hello.jsa
       v
    hello.jsa              (static archive)
       |
       | java -XX:SharedArchiveFile=hello.jsa
       | -Xlog:class+load=info -cp hello.jar demo.Hello
       v
demo.Hello loaded from shared objects file
```

Ba điểm dễ sai:

1. Phải có **JAR để JVM nạp được lớp ứng dụng** cả ở bước thu classlist và bước dump. Việc tự chạy một file `.java` đơn lẻ không phải cách minh họa tốt cho static AppCDS.
2. Cần giữ **classpath và nguồn JAR tương thích** giữa giai đoạn tạo và giai đoạn sử dụng archive.
3. Archive chỉ là **tài nguyên tối ưu**. Đừng xóa JAR gốc sau khi tạo `.jsa`; JVM vẫn cần classpath ứng dụng và có thể phải nạp thêm lớp không nằm trong archive.

## 5. Ví dụ Java 17+ độc lập: biên dịch, đóng JAR, dump và nạp archive

Ví dụ này chỉ dùng Java SE và công cụ JDK. Tạo cấu trúc thư mục:

```text
appcds-demo/
└── src/
    └── demo/
        └── Hello.java
```

Lưu mã vào file **`src/demo/Hello.java`**:

```java
package demo;

public final class Hello {
    public static void main(String[] args) {
        System.out.println("AppCDS OK");
    }
}
```

### 5.1. Bước A: Tạo `hello.jar`

Tại thư mục `appcds-demo`, chạy:

```bash
mkdir -p classes
javac --release 17 -encoding UTF-8 -d classes src/demo/Hello.java
jar --create --file hello.jar -C classes .
```

Lệnh `mkdir -p` dành cho POSIX shell. Nếu dùng PowerShell:

```powershell
New-Item -ItemType Directory -Path classes -Force
javac --release 17 -encoding UTF-8 -d classes src/demo/Hello.java
jar --create --file hello.jar -C classes .
```

Kiểm tra JAR có lớp:

```bash
jar --list --file hello.jar
```

Danh sách có `demo/Hello.class`. Vì chúng ta chạy bằng `-cp hello.jar demo.Hello` nên **không cần** thuộc tính `Main-Class` trong JAR manifest. Nếu thay sang `java -jar hello.jar`, bạn phải có manifest phù hợp và kiểm soát đúng classpath của ứng dụng; đừng đổi kiểu launch tùy tiện giữa các giai đoạn.

### 5.2. Bước B: Thu classlist

```bash
java -Xshare:off -XX:DumpLoadedClassList=hello.classlist \
     -cp hello.jar demo.Hello
```

Kết quả stdout của ứng dụng:

```text
AppCDS OK
```

File `hello.classlist` được tạo. Nó chứa thông tin lớp của JVM và dòng liên quan tới `demo/Hello`. Bạn có thể kiểm tra bằng công cụ tìm kiếm text của hệ điều hành (ví dụ `grep` trên POSIX hoặc `Select-String` trên PowerShell).

**Vì sao chạy thử ứng dụng trước khi dump?** JVM cần biết **những lớp nào ứng dụng thực sự dùng**. Với ứng dụng thật, phải thu classlist trên một workload đại diện cho startup và các đường đi quan trọng; classlist được tạo từ một đường đi quá nhỏ sẽ không bao phủ mọi lớp cần tối ưu.

### 5.3. Bước C: Tạo kho tĩnh bằng `-Xshare:dump`

```bash
java -Xshare:dump \
     -XX:SharedClassListFile=hello.classlist \
     -XX:SharedArchiveFile=hello.jsa \
     -cp hello.jar
```

Hoặc một dòng chạy được trên PowerShell/CMD/POSIX:

```text
java -Xshare:dump -XX:SharedClassListFile=hello.classlist -XX:SharedArchiveFile=hello.jsa -cp hello.jar
```

**Kết quả thành công:** file `hello.jsa` được tạo, có kích thước lớn hơn 0. **Lệnh dump không in `AppCDS OK`**, vì nó không chạy `main` của `demo.Hello`. Dung lượng và dòng thông báo JVM không phải hằng số có thể dự đoán qua các bản JDK.

**Quan sát thực tế đã kiểm thử với OpenJDK 24.0.2:** kho tĩnh được tạo thành công, có dung lượng khoảng 10 MB trong môi trường thử nghiệm. Đây chỉ là kích thước của **ví dụ và JDK đó**, không phải size yêu cầu của AppCDS.

### 5.4. Bước D: Khởi chạy với archive

```bash
java -XX:SharedArchiveFile=hello.jsa \
     -cp hello.jar demo.Hello
```

Stdout:

```text
AppCDS OK
```

Điều này xác nhận **chương trình vẫn chạy đúng**, nhưng **chưa đủ chứng minh lớp `demo.Hello` được lấy từ archive**. Một JVM không dùng CDS vẫn có thể in chính xác dòng đó.

### 5.5. Bước E: Kiểm tra lớp thật sự được nạp từ archive

```bash
java -XX:SharedArchiveFile=hello.jsa \
     -Xlog:class+load=info \
     -cp hello.jar demo.Hello
```

Lệnh trên tạo **nhiều dòng log** nên không nên so toàn bộ stdout từng ký tự. Tìm dòng chứa `demo.Hello` và `source: shared objects file`.

**Đoạn log/kết quả quan trọng đã được xác minh:**

```text
[info][class,load] demo.Hello source: shared objects file
AppCDS OK
```

Trong log thực tế có thể có prefix thời gian như `[0.036s]`. Không khóa thời gian hoặc thứ tự các log nền tảng trong test. Chỉ kiểm tra **lớp mục tiêu**:

- tên class: `demo.Hello`;
- source: `shared objects file`;
- ứng dụng: `AppCDS OK`.

Trên POSIX shell, có thể lọc:

```bash
java -XX:SharedArchiveFile=hello.jsa \
     -Xlog:class+load=info -cp hello.jar demo.Hello \
     | grep -E 'demo.Hello|AppCDS OK'
```

Trên PowerShell:

```powershell
java -XX:SharedArchiveFile=hello.jsa -Xlog:class+load=info -cp hello.jar demo.Hello |
    Select-String -Pattern 'demo.Hello','AppCDS OK'
```

Bài kiểm thử trong môi trường OpenJDK 24.0.2 đã xác nhận cả `hello.classlist` và `hello.jsa` được tạo, và dòng `demo.Hello source: shared objects file` xuất hiện. Nếu log chỉ nói lớp đến từ `file:/.../hello.jar`, cần điều tra vì **lớp đó chưa thực sự được load từ archive** trong lần chạy này.

## 6. Ràng buộc classpath và file JAR

### 6.1. Static AppCDS cần nguồn lớp phù hợp

Với quy trình static archive có lớp ứng dụng, tài liệu `java` mới nhất nêu rõ **classpath dùng khi thu/dump phải chứa các JAR**, không dựa vào các thư mục `classes/` không rỗng.

**Phù hợp:**

```bash
java -Xshare:dump -XX:SharedClassListFile=hello.classlist \
     -XX:SharedArchiveFile=hello.jsa -cp hello.jar
```

**Không chọn cho bài thực hành static AppCDS:**

```bash
# Một thư mục classes/ không rỗng không phải nguồn JAR.
java -Xshare:dump -XX:SharedClassListFile=hello.classlist \
     -XX:SharedArchiveFile=hello.jsa -cp classes/
```

Vì lý do đó, ví dụ **biên dịch rồi đóng JAR trước khi thu classlist**, không dừng ở việc chạy `java -cp classes demo.Hello`.

Với ứng dụng dùng nhiều JAR, classpath có thể có dạng:

```text
app.jar:lib/a.jar:lib/b.jar        (POSIX)
app.jar;lib\a.jar;lib\b.jar        (Windows)
```

Ký tự phân cách tùy hệ điều hành; một phần classpath là đường dẫn đến JAR. Nên dùng công cụ build hoặc script triển khai tạo classpath **ổn định** thay vì dựa vào expansion không có thứ tự rõ ràng.

### 6.2. Classpath tại dump và runtime

Theo tài liệu Oracle/OpenJDK:

- Classpath dùng ở bước tạo archive phải **giống hoặc là tiền tố** của classpath dùng khi chạy.
- Các JAR đã tham gia archive **không được tự thay đổi nội dung** sau khi dump.
- Nếu archive và runtime không tương thích, JVM có thể bỏ qua archive hoặc không khởi động với chế độ kiểm thử bắt buộc; hãy đọc log cụ thể.

Ví dụ:

```text
DUMP: app.jar:lib/a.jar
RUN : app.jar:lib/a.jar:lib/b.jar
```

Một classpath runtime mở rộng bằng phần tử ở cuối có thể phù hợp với nguyên tắc **prefix**; điều này không cho phép tự đổi thứ tự hoặc đổi JAR đã có trong đoạn prefix.

**Không dùng** một archive tạo với `app.jar` rồi khởi chạy mặc định trên một `app.jar` mới đã sửa mà cho rằng JVM vẫn dùng các metadata cũ. Trong build/deploy, giữ archive gắn với **cùng bộ artifact đã dump**.

### 6.3. Đối với module path

Các bản Java mới hơn có hỗ trợ CDS đối với **modular JARs** trên module path; JDK 11 mở rộng một số khả năng so với AppCDS đầu tiên. Nhưng **exploded modules** và các tùy chọn module có thể có những giới hạn riêng.

Nếu dự án chạy theo `--module-path`/`-m`, hãy đối chiếu **phần Restrictions on Class Path and Module Path** của tài liệu `java` thuộc JDK đang sử dụng; đừng áp dụng máy móc bộ lệnh `-cp hello.jar demo.Hello` cho một ứng dụng module phức tạp.

## 7. Tính tương thích của archive với JDK và môi trường

### 7.1. Một file `.jsa` không phải artifact độc lập với JDK

CDS archive gắn với một **JDK build cụ thể** và có các ràng buộc về kiến trúc/hệ điều hành và cấu hình khi tạo. Vì vậy, không nên:

- tạo `hello.jsa` trên một JDK rồi đưa qua JDK khác tùy ý;
- nâng JDK từ bản update cũ sang mới mà mặc định archive vẫn phù hợp;
- dùng một archive duy nhất cho Windows, Linux, x64 và ARM64 mà không kiểm tra;
- chỉ dựa vào `java -version` chứa cùng số feature (ví dụ đều là 25) để kết luận tương thích.

**Quy tắc vận hành:** tạo archive trong môi trường gần tương đương nơi chạy, với **cùng bản build JDK và các application JARs**, rồi kiểm tra archive trong pipeline/deployment thật. Khi thay binary JDK, patch release, classpath hoặc JAR nội dung, nên **tái tạo và kiểm thử lại archive**.

### 7.2. Container và image

Với container:

1. Pin base image có nguồn rõ ràng và phù hợp security policy.
2. Build JAR và CDS archive trong môi trường dùng cùng JDK build.
3. Đảm bảo file archive và JAR được copy vào image với đường dẫn phù hợp.
4. Dùng classpath thống nhất ở bước dump và run.
5. Sau khi thay base image/JDK updates, **rebuild archive** và chạy smoke test xác minh lớp được load từ shared archive.
6. Đánh giá startup, memory và chi phí lưu archive so với image chưa dùng AppCDS.

Không đưa archive chưa được kiểm chứng vào một image cố định rồi quên cập nhật sau các bản vá JDK.

### 7.3. Quyền truy cập và tính toàn vẹn

CDS archive chứa dữ liệu JVM sẽ dùng để tăng tốc việc nạp lớp. Nó là **artifact cần được bảo vệ**, không phải file để user tùy ý sửa.

- Đặt file trong thư mục có quyền phù hợp.
- Không tải các file `.jsa` không đáng tin từ bên ngoài để đưa trực tiếp vào production.
- Chỉ publish archive theo cùng pipeline phát hành có xác minh nguồn JAR/JDK.
- Có thể dùng tùy chọn `-XX:+VerifySharedSpaces` khi cần kiểm tra CRC32 để phát hiện **hư hỏng vô ý** của file archive; CRC32 **không phải chữ ký mật mã** và không thay thế kiểm tra integrity/provenance.

Javadoc/launcher guide hiện hành nhấn mạnh người dùng phải kiểm soát khả năng bên không có thẩm quyền sửa archive.

## 8. Các tình huống lỗi và cách tìm nguyên nhân

### 8.1. Không có file `hello.classlist`

Kiểm tra:

- lần chạy thu classlist có thực sự khởi động JVM và kết thúc bình thường không;
- tùy chọn `-XX:DumpLoadedClassList=...` có đứng trước tên main class không;
- thư mục đích có quyền ghi không;
- classpath có đúng JAR và main class không.

Lưu ý về vị trí option:

```bash
# Đúng: tùy chọn JVM đứng trước main class.
java -XX:DumpLoadedClassList=hello.classlist -cp hello.jar demo.Hello
```

Nếu đặt `-XX:DumpLoadedClassList=...` **sau** `demo.Hello`, nó sẽ là **đối số của `main(String[] args)`**, không còn là tùy chọn của JVM.

### 8.2. Có classlist nhưng thiếu lớp ứng dụng

Kiểm tra classlist chứa `demo/Hello` hay không. Nếu không, lần chạy profiling có thể chưa nạp lớp cần tối ưu, hoặc chương trình dùng một launcher/classloader với hành vi khác.

Với ứng dụng thật, thu classlist trong **workload đại diện**, không chỉ chạy `--help` hoặc màn hình chào. Những class load muộn chỉ xuất hiện sau khi tính năng đó thực sự được kích hoạt.

### 8.3. Dump thất bại vì classpath, classlist hoặc artifact

Kiểm tra:

- classpath ở bước dump có chỉ chứa các JAR phù hợp không;
- `hello.classlist` đúng định dạng và được sinh từ đúng môi trường không;
- source JAR có bị thay đổi kể từ khi tạo classlist không;
- tên và đường dẫn lớp có khớp không;
- JVM có báo lỗi không hỗ trợ/cấm một classpath hoặc module option nào không;
- file `hello.jsa` có nằm trong thư mục có quyền ghi không.

**Không tự sửa classlist không rõ định dạng bằng cách xóa bừa các dòng metadata** nếu chưa hiểu nguyên nhân. Với dự án bình thường, cách an toàn hơn là **thu lại classlist từ artifact đúng** và dump lại.

### 8.4. File archive có tồn tại nhưng runtime không sử dụng

Đây là lỗi quan trọng nhất vì **stdout ứng dụng vẫn có thể đúng**.

Chạy:

```bash
java -XX:SharedArchiveFile=hello.jsa \
     -Xlog:class+load=info \
     -cp hello.jar demo.Hello
```

Tìm `demo.Hello source: shared objects file`. Nếu lớp được nạp từ JAR, xem log CDS và kiểm tra:

- JDK build đang chạy có giống lúc dump không;
- file JAR có bị sửa hoặc đổi tên/vị trí không;
- classpath có còn cùng thứ tự/prefix không;
- một tùy chọn JVM khác có vô hiệu hóa hoặc hạn chế CDS không;
- archive có bị hỏng hoặc thiếu quyền đọc không.

Có thể bật thêm `-Xlog:cds=info` hoặc mức log cao hơn khi điều tra. Đừng bật log class loading chi tiết mặc định trên production nếu nó gây quá nhiều log/noise.

### 8.5. `-Xshare:on` làm JVM không khởi động

Điều đó đúng với **chế độ bắt buộc**: archive không dùng được thì quá trình khởi động thất bại. Không “khắc phục” bằng cách bắt production dùng `on` để chắc chắn có AppCDS. Dùng `on` cho thử nghiệm fail-fast có chủ đích; production nên chọn cơ chế fallback hợp lý và theo dõi kết quả tối ưu.

### 8.6. Startup không nhanh hơn đáng kể

Có thể vì:

- lớp được archive chỉ là một phần nhỏ so với tổng startup cost;
- workload bị chi phối bởi I/O, mạng, khởi tạo framework, kết nối DB, TLS, JIT, DI hoặc business initialization;
- classlist quá ít, ứng dụng chưa load các lớp quan trọng trong profile run;
- archive không thật sự được dùng;
- nền tảng đo không ổn định hoặc kết quả bị nhiễu bởi OS file cache/JIT warmup.

**Không khẳng định** việc tạo archive tự động giảm startup 30% hoặc một tỷ lệ cố định. Đo theo đúng kịch bản **cold startup**, **warm startup**, memory và số process; chọn số lần lặp đủ lớn để so sánh có ý nghĩa.

## 9. So sánh cách vận hành trong các JDK hiện đại

| Cách làm | Tùy chọn tiêu biểu | Khi cân nhắc |
| --- | --- | --- |
| **Static CDS/AppCDS** | `-Xshare:dump`, `-XX:SharedClassListFile` | Chủ động tạo archive tĩnh từ classlist; cần kiểm soát rõ dump |
| **Dynamic CDS** | `-XX:ArchiveClassesAtExit` | Muốn tạo archive bổ sung khi ứng dụng kết thúc mà không duy trì classlist thủ công |
| **Auto-create CDS** | `-XX:+AutoCreateSharedArchive` | Muốn JVM tự xử lý tạo/tái tạo dynamic archive theo điều kiện được hỗ trợ |
| **JDK AOT cache (JDK 24+)** | `-XX:AOTCacheOutput` và `-XX:AOTCache` | Khi cần các tối ưu AOT mới hơn, nên xem tài liệu và công cụ build/framework mục tiêu |
| **CDS mặc định** | Không cần tự tạo AppCDS archive ở nhiều JDK | Tận dụng các lớp core JDK đã có trong default CDS archive |

**Tương thích với Special Note:** những tùy chọn liệt kê đều có cơ chế còn được tài liệu Java hiện hành mô tả, nhưng **mức hỗ trợ và lựa chọn nên dùng phụ thuộc JDK cụ thể**. Static dump là **một lựa chọn còn có giá trị**, không phải phương án mặc định tối ưu của mọi dự án.

### 9.1. Vì sao AOT cache cần được xem xét?

Tài liệu `java` của JDK 27 nói rằng AOT cache (giới thiệu từ JDK 24) có thể chứa nhiều loại dữ liệu tối ưu hơn CDS truyền thống, ví dụ lớp và heap objects được chuẩn bị trước. Những bản JDK mới tiếp tục mở rộng kiểu dữ liệu/tối ưu của AOT cache.

Với một ứng dụng mới trên JDK 25+, AOT cache có thể cho startup/warm-up tốt hơn. Nên đánh giá qua benchmark, yêu cầu của framework, tính tương thích GC/agents và quy trình training. Nhưng đây **không phải** lý do để gọi `-Xshare:dump` “đã bị gỡ” hoặc không còn chức năng trên JDK mới.

### 9.2. Không bê nguyên cấu hình runtime mới sang Java 10

`-XX:ArchiveClassesAtExit`, `-XX:+AutoCreateSharedArchive` và AOT cache được bổ sung **sau Java 10**. Nếu bài thực hành cần tương thích đúng **JDK 10**, hãy tập trung quy trình **classlist → `-Xshare:dump` → `SharedArchiveFile`** được JEP 310 giới thiệu. Nếu dùng JDK 17+ hoặc 24+, bạn có thể cân nhắc các cách tiện hơn tùy điều kiện.

Java 10 không được khuyến nghị làm runtime production mới trong năm 2026 khi không có kênh bảo trì hiện hành rõ ràng. Học cơ chế Java 10 trên JDK được duy trì vẫn phù hợp vì các API/flag chính còn tồn tại.

## 10. QA vận hành: kiểm tra đúng những gì

Một bộ QA tốt không chỉ kiểm tra `hello.jsa` tồn tại.

| Kiểm tra | Ý nghĩa |
| --- | --- |
| `java --version` / build metadata | Xác định đúng bản JDK đang dùng |
| `jar --list --file hello.jar` | JAR có các class được kỳ vọng |
| `hello.classlist` chứa `demo/Hello` | Giai đoạn profiling thực sự nạp lớp ứng dụng |
| Lệnh `-Xshare:dump` exit code 0 | Quá trình tạo archive hoàn tất |
| `hello.jsa` có kích thước lớn hơn 0 | Artifact đã được tạo |
| Chạy app với `SharedArchiveFile` in `AppCDS OK` | Không làm hỏng chức năng ví dụ |
| Log `demo.Hello source: shared objects file` | **Chứng minh lớp mục tiêu lấy từ archive** |
| So startup có/không archive với cùng workload | Ước lượng lợi ích hiệu năng thực tế |
| Thay JDK/JAR rồi test tái tạo | Tránh sử dụng archive lỗi thời |

### 10.1. Gợi ý kiểm thử tự động

Trong CI:

1. Build ứng dụng và ghi version đầy đủ của JDK.
2. Chạy workload đại diện để tạo classlist.
3. Dump archive, kiểm tra exit code/file size.
4. Chạy smoke test với archive, lấy log class loading.
5. Assertion chỉ kiểm tra **các class mục tiêu** thực sự được nạp từ `shared objects file`.
6. Nếu archive không hợp lệ, **đánh dấu job tối ưu thất bại** thay vì xuất bản nó.
7. Publish JAR, archive và metadata về JDK build/image cùng một artifact set.
8. Tái tạo archive khi pipeline đổi base image/JDK hoặc JAR.

Không bắt CI so đúng toàn bộ output `-Xlog:class+load`: log còn chứa rất nhiều lớp hệ thống với thứ tự/thời điểm khác nhau giữa các JDK.

### 10.2. Hiệu năng phải đo đúng mục đích

Một kết luận có ý nghĩa nên gồm:

- trung vị và phân vị startup của nhiều lần chạy;
- phân biệt cache nóng/lạnh nếu có;
- trạng thái tải CPU, I/O, container memory;
- cùng JDK/JAR, same arguments và workload;
- bộ nhớ RSS hoặc metric phù hợp nếu mục tiêu là footprint.

Cũng cần tính **chi phí build, kích thước archive, thời gian tạo và công sức quản lý**. Với ứng dụng chỉ khởi động hiếm khi và workload runtime rất dài, lợi ích startup có thể không đáng đổi lấy sự phức tạp vận hành.

## 11. Những ngộ nhận phổ biến

**Ngộ nhận 1 — “Gọi `java -Xshare:dump` là đã chạy app với AppCDS.”**  
Sai. `dump` tạo archive; ứng dụng được chạy bằng archive ở lệnh khác với `-XX:SharedArchiveFile`.

**Ngộ nhận 2 — “Chỉ cần có một `hello.jar`, không cần classlist.”**  
Với quy trình **static AppCDS có chọn lớp ứng dụng**, cần classlist phù hợp để JVM biết những lớp đã nạp. Nếu bỏ classlist, có thể chỉ tạo archive mặc định cho lớp nền tảng mà không có những class nghiệp vụ mong muốn.

**Ngộ nhận 3 — “Đã thấy `AppCDS OK` là chắc chắn archive được dùng.”**  
Sai. Ứng dụng không dùng archive cũng in dòng đó. Cần log lớp `source: shared objects file`.

**Ngộ nhận 4 — “File `.jsa` thay thế được JAR.”**  
Sai. CDS archive chứa dữ liệu lớp tối ưu; JVM vẫn cần nguồn lớp/classpath đúng và có thể nạp lớp không nằm trong archive.

**Ngộ nhận 5 — “Archive sinh bằng JDK 24 dùng được với mọi JDK 25/27.”**  
Sai. Archive phụ thuộc JDK build và môi trường. Phải tạo lại, kiểm thử lại sau những thay đổi liên quan.

**Ngộ nhận 6 — “Classpath chứa directory `classes/` là tương đương JAR trong static dump.”**  
Sai trong quy trình nêu tại tài liệu launcher hiện hành: nonempty directories có giới hạn; dùng JAR thích hợp cho ứng dụng.

**Ngộ nhận 7 — “`-Xshare:on` là cài đặt production an toàn nhất.”**  
Sai. Nó biến khả năng dùng CDS thành điều kiện khởi động. Tài liệu khuyến cáo chỉ dùng để kiểm thử.

**Ngộ nhận 8 — “CDS là AOT native compiler.”**  
Sai. CDS giảm công đoạn xử lý metadata lớp, không tự biến toàn bộ ứng dụng thành executable native hoặc lưu mọi mã đã được JIT tối ưu.

**Ngộ nhận 9 — “AppCDS luôn cải thiện startup với phần trăm cố định.”**  
Sai. Lợi ích phụ thuộc workload, số lớp được archive, dữ liệu đã được map, hiệu năng I/O và nhiều yếu tố runtime.

**Ngộ nhận 10 — “Static archive đã bị xóa ở JDK 27.”**  
Sai. JDK 27 vẫn mô tả `-Xshare:dump`. Tuy nhiên, các tùy chọn AOT mới nên được đánh giá nếu phù hợp.

## 12. Bài tập tự kiểm tra

**Câu 1.** Để tạo static archive từ `hello.jar`, hai file đầu vào chính trong bước dump là gì?  
**Đáp án:** JAR ứng dụng chứa các lớp và `hello.classlist` được thu từ một lần chạy phù hợp. Lệnh `-Xshare:dump` dùng `-XX:SharedClassListFile` và `-cp` để tham chiếu chúng, ghi ra `hello.jsa`.

**Câu 2.** Tại sao ở bước thu classlist lại có `-Xshare:off`?  
**Đáp án:** Tắt CDS trong lần thu dữ liệu để lớp thực sự được nạp trong workload, cho phép tạo classlist phù hợp với chương trình.

**Câu 3.** Có cần thêm tên main class `demo.Hello` ở cuối lệnh `-Xshare:dump` không?  
**Đáp án:** Không. Dump là chế độ tạo archive của JVM, không gọi `main()`.

**Câu 4.** File `hello.jsa` đã xuất hiện, nhưng chạy app vẫn in `AppCDS OK`. Đã đủ bằng chứng AppCDS hoạt động chưa?  
**Đáp án:** Chưa. Phải xác minh log tải lớp `demo.Hello source: shared objects file` hoặc tín hiệu CDS tương đương.

**Câu 5.** `-Xshare:on` có nên bật trên mọi production JVM?  
**Đáp án:** Không. Nếu archive không dùng được, nó có thể làm JVM thoát. Dùng `on` cho kiểm tra có chủ đích, còn production nên có chính sách fallback phù hợp.

**Câu 6.** Khi cập nhật `hello.jar` hoặc JDK build, archive cũ có chắc dùng được không?  
**Đáp án:** Không. Phải tái tạo và kiểm thử archive với cùng JDK/JAR phù hợp.

**Câu 7.** Vì sao nên đóng JAR trước khi chạy `-Xshare:dump`?  
**Đáp án:** Static AppCDS có giới hạn với thư mục classpath không rỗng và yêu cầu nguồn JAR phù hợp cho lớp ứng dụng.

**Câu 8.** Sự khác nhau giữa `SharedClassListFile` và `SharedArchiveFile`?  
**Đáp án:** `SharedClassListFile` là danh sách lớp **đầu vào của dump**; `SharedArchiveFile` là đường dẫn archive được **ghi ở dump** và **đọc ở runtime**.

**Câu 9.** Có phải AppCDS lưu lại mọi đối tượng Java tồn tại khi profiling không?  
**Đáp án:** Không. Static AppCDS tập trung dữ liệu lớp; đừng xem nó là snapshot toàn bộ heap hoặc application state.

**Câu 10.** Vì sao ứng dụng JDK 25+ nên xem thêm AOT cache?  
**Đáp án:** AOT cache mới có thể lưu nhiều loại dữ liệu tối ưu hơn CDS truyền thống và phù hợp với công cụ/framework hiện đại, nhưng vẫn phải benchmark và kiểm tra tính tương thích.

## 13. Checklist ngắn để triển khai

- **Build:** `hello.jar` có đúng lớp cần chạy không?
- **Profile:** `hello.classlist` được thu bằng workload đại diện và chứa lớp mục tiêu không?
- **Dump:** `-Xshare:dump` có tạo `hello.jsa` thành công không?
- **Run:** `-XX:SharedArchiveFile` có trỏ đúng archive với đúng classpath không?
- **Verify:** log class load có `source: shared objects file` cho lớp ứng dụng không?
- **Compatibility:** bản JDK, OS/CPU, JAR và các JVM options có phù hợp khi dump/run không?
- **Security:** archive có quyền truy cập và provenance phù hợp không?
- **Performance:** số liệu startup/footprint có chứng minh lợi ích với workload thật không?
- **Lifecycle:** có rebuild archive sau khi nâng JDK hoặc dependency không?
- **Alternatives:** đã cân nhắc dynamic CDS hoặc AOT cache nếu đang dùng JDK mới chưa?

## 14. Ghi nhớ

1. **AppCDS có từ Java 10 (JEP 310)**; quy trình **static archive với `-Xshare:dump` vẫn còn trong tài liệu JDK hiện hành**.
2. Tạo archive cho ứng dụng theo luồng **JAR → chạy thu `classlist` → `-Xshare:dump` ghi `.jsa` → chạy với `SharedArchiveFile`**.
3. `-XX:DumpLoadedClassList` ghi danh sách lớp đã nạp; `-XX:SharedClassListFile` đọc danh sách ở dump; `-XX:SharedArchiveFile` chỉ định file archive ở dump/runtime.
4. **Không đồng nhất “archive tồn tại” với “archive được dùng”.** Kiểm tra `-Xlog:class+load=info` và nguồn `shared objects file` của lớp ứng dụng.
5. Static AppCDS phụ thuộc JDK build, JAR/classpath, OS/architecture và các JVM options liên quan; **thay những thứ đó thì rebuild và kiểm thử**.
6. `-Xshare:on` dành cho test bắt buộc; production nên tránh điều kiện khởi động cứng phụ thuộc archive.
7. Lợi ích AppCDS là **tùy workload**, không cam kết một mức tăng tốc cố định.
8. Trên JDK 24+ đã có **AOT cache**; AppCDS static vẫn được hỗ trợ nhưng là một lựa chọn trong nhiều cơ chế tối ưu startup hiện hành.

## Tài liệu tham khảo chính thức còn áp dụng

- **OpenJDK JEP 310 — Application Class-Data Sharing**, được triển khai trong JDK 10: https://openjdk.org/jeps/310
- **Java SE 27 — The `java` Command, Application Class Data Sharing**, quy trình static archive bằng `-Xshare:dump`, dynamic archive, classpath restrictions, log: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- **OpenJDK JDK source — `java.md`**, tài liệu launcher được duy trì cùng mã nguồn OpenJDK: https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md
- **Dev.java — CDS and AppCDS in HotSpot**, hướng dẫn phân biệt static/dynamic CDS: https://dev.java/learn/jvm/cps-appcds/
- **Java SE 27 — Ahead-of-Time Cache**, xem phần AOT cache trong tài liệu `java`: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- **OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking**, những tối ưu hiện đại hơn: https://openjdk.org/jeps/483
- **Oracle Java SE 27 — `-XX:+VerifySharedSpaces`**, kiểm tra integrity của archive: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
