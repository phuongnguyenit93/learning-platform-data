# Thu danh sách lớp bằng `-XX:DumpLoadedClassList` khi vận hành AppCDS (Java 10 và JDK hiện đại)

## 1. Mục tiêu: biết JVM đã nạp những lớp nào để tối ưu thời gian khởi động

Ứng dụng Java thường tải nhiều lớp (`class`) khi khởi động: các lớp trong Java runtime, thư viện phụ thuộc và chính mã ứng dụng. Quá trình nạp, đọc và xử lý metadata của lớp có thể góp phần vào chi phí **startup** và mức tiêu thụ bộ nhớ, đặc biệt với dịch vụ có thời gian sống ngắn hoặc nhiều tiến trình JVM cùng chạy.

**Class Data Sharing (CDS)** cho phép JVM lưu trữ một số metadata của lớp trong archive có thể sử dụng lại. **Application Class Data Sharing (AppCDS)** mở rộng khả năng này tới các lớp ứng dụng và thư viện khi đáp ứng điều kiện. Một cách vận hành **static CDS archive thủ công** là:

1. Chạy ứng dụng đại diện với flag `-XX:DumpLoadedClassList=<file>` để **ghi nhận những lớp đã được tải**.
2. Dùng tệp danh sách lớp (`class list`) làm đầu vào để **tạo archive `.jsa`**.
3. Khởi chạy ứng dụng với archive và xác nhận một số lớp được nạp từ **shared objects file**.

Lệnh ở bước 1:

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
     -cp app.jar demo.App
```

Lệnh này **chạy ứng dụng thật** `demo.App`, ghi danh sách lớp vào `app.classlist` và **không tự sinh file `.jsa`**.

**Đây là điểm cốt lõi của bài học:** `-XX:DumpLoadedClassList` thu thập **class list**, không phải bản thân CDS archive; hai loại tệp có mục đích và cách tạo khác nhau.

### Phạm vi và tính hiện hành

- AppCDS được đưa vào OpenJDK theo **JEP 310 (Java 10)** và là kiến thức vận hành còn giá trị.
- Flag **`-XX:DumpLoadedClassList` vẫn được tài liệu hóa trong `java` launcher của JDK 26** cho quy trình tạo **static CDS archive** thủ công.
- Từ các JDK mới hơn, có lựa chọn **dynamic CDS** và **AOT cache** đơn giản hơn trong nhiều tình huống. Bài sẽ phân biệt rõ, **không khuyến nghị quy trình nhiều bước là lựa chọn duy nhất hoặc luôn tối ưu**.
- `-XX:+UseAppCDS` là một flag **đã obsolete từ JDK 11**. **Không sử dụng nó trong lệnh hiện hành**.
- Với các hướng dẫn AOT cache `-XX:AOTCacheOutput` ở cuối bài, cần **JDK 25+**; đừng sao chép lệnh đó sang JDK 17 hoặc 24. Quy trình thu class list và tạo static CDS ở các mục chính được kiểm chứng với JDK 24.

Các câu lệnh minh họa dành cho **HotSpot/OpenJDK có hỗ trợ CDS**, không được mặc định mọi Java implementation hoặc bản phân phối đều hỗ trợ chính xác tập JVM flags này.

## 2. Kết quả học tập

Sau bài, bạn có thể:

1. Giải thích CDS, AppCDS và vai trò của **class list**.
2. Viết đúng cú pháp `-XX:DumpLoadedClassList=app.classlist` và biết đặt JVM option ở đâu trong lệnh `java`.
3. Hiểu **ứng dụng phải được chạy thật** để JVM quan sát các lớp được load.
4. Phân biệt class list `.classlist`, JAR `.jar`, static archive `.jsa` và AOT cache `.aot`.
5. Chuẩn bị ứng dụng demo và đóng gói JAR sao cho classpath thích hợp để tạo static archive.
6. Xác nhận trong class list có cả lớp runtime và lớp ứng dụng.
7. Tạo static CDS archive bằng `-Xshare:dump`, `-XX:SharedClassListFile` và `-XX:SharedArchiveFile`.
8. Khởi chạy với archive và kiểm tra `-Xlog:class+load=info`.
9. Hiểu một lớp được **thu vào class list** không đồng nghĩa chắc chắn được **đưa vào archive** hoặc **nạp lại từ archive**.
10. Biết giới hạn liên quan classpath, thay đổi JAR, JDK build, custom class loaders và các tác nhân instrumentation.
11. Chọn cách xử lý phù hợp khi ứng dụng có nhiều nhánh khởi tạo, khối lượng công việc khác nhau hoặc tài nguyên động.
12. Nhận diện các lý do archive không được dùng và phân biệt điều đó với lỗi logic của ứng dụng.
13. Tránh áp dụng các flag cũ đã obsolete trong Java hiện đại.
14. So sánh cách thu class list thủ công với `-XX:ArchiveClassesAtExit`, `jcmd VM.cds` và AOT cache JDK 25+.
15. Thiết lập một bài đo startup đáng tin cậy thay vì khẳng định “CDS luôn nhanh hơn X%”.

## 3. Bốn khái niệm không được nhầm

| Khái niệm | Nội dung | Vai trò |
| --- | --- | --- |
| **Ứng dụng/JAR** `app.jar` | Bytecode của ứng dụng (và các thư viện theo classpath tương ứng) | Nguồn chương trình được JVM chạy |
| **Class list** `app.classlist` | Ghi nhận lớp và thông tin liên quan đã quan sát trong training run | Đầu vào cho quy trình tạo static CDS |
| **Static CDS archive** `app.jsa` | Dữ liệu CDS đã được JVM xây dựng để dùng lại | Được nạp bởi `-XX:SharedArchiveFile` |
| **AOT cache** `app.aot` | Container các artifact tối ưu hóa ahead-of-time trên JDK hỗ trợ | Một workflow tối ưu startup hiện đại khác |

Sơ đồ:

```text
                     app.jar
                        |
                        | 1) java -Xshare:off
                        |    -XX:DumpLoadedClassList=app.classlist
                        v
                 app.classlist
                        |
                        | 2) java -Xshare:dump
                        |    -XX:SharedClassListFile=app.classlist
                        |    -XX:SharedArchiveFile=app.jsa
                        v
                    app.jsa
                        |
                        | 3) java -XX:SharedArchiveFile=app.jsa
                        v
               App khởi động với CDS
```

**Không lấy số lượng dòng của `.classlist` làm số lượng lớp chắc chắn được chia sẻ từ `.jsa`.** Các điều kiện archiving và cách xử lý class loader có thể khiến chỉ một phần các lớp quan sát được thực sự được lưu hoặc nạp lại từ archive.

## 4. Cú pháp đầy đủ của bước thu danh sách lớp

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
     -cp app.jar demo.App
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `java` | Khởi chạy ứng dụng bằng JVM |
| `-Xshare:off` | Tắt sử dụng CDS archive trong **training run** theo ví dụ quy trình static CDS của Oracle |
| `-XX:DumpLoadedClassList=app.classlist` | Đặt tên/đường dẫn file dùng để ghi danh sách lớp được nạp |
| `-cp app.jar` | Cấu hình classpath chứa JAR ứng dụng |
| `demo.App` | Lớp chứa `main(String[])` được thực thi |
| `app.classlist` | **File text class list**, chưa phải archive |
| `app.jsa` | Archive sẽ được sinh ở bước **khác** |

### Đặt JVM option trước tên main class

```bash
# Đúng: flag là tùy chọn của JVM launcher
java -XX:DumpLoadedClassList=app.classlist -cp app.jar demo.App

# Không tương đương:
java -cp app.jar demo.App -XX:DumpLoadedClassList=app.classlist
```

Ở dòng thứ hai, các giá trị sau tên main class là **đối số dành cho ứng dụng**. Nếu chương trình `main` không tự diễn giải chúng thì không có ý nghĩa với JVM; cũng không tạo class list như mong muốn.

### Ý nghĩa của `-Xshare:off`

Trong workflow static archive đã tài liệu hóa, Oracle dùng `-Xshare:off` để chạy training mà không dùng archive có sẵn. Flag này **không phải cú pháp bắt buộc của mọi kiểu profiling class** và không nên đưa vào **lần chạy production muốn sử dụng CDS**, vì `-Xshare:off` tắt CDS.

Ở bước sử dụng `app.jsa` sau đó, bỏ `-Xshare:off`; khi cần kiểm chứng nghiêm ngặt có thể dùng `-Xshare:on` để yêu cầu sử dụng archive.

### Đường dẫn classlist

Giá trị bên phải dấu `=` có thể là một đường dẫn. Nếu là đường dẫn tương đối như `app.classlist` thì file được ghi tại vị trí tương ứng với **working directory** của lệnh `java`, không nhất thiết cùng thư mục chứa file `app.jar` nếu bạn chạy từ chỗ khác.

Ví dụ:

```bash
java -Xshare:off -XX:DumpLoadedClassList=out/app.classlist \
     -cp app.jar demo.App
```

Thư mục `out` cần tồn tại và tiến trình phải được cấp quyền ghi. Nếu đường dẫn có khoảng trắng, quote **toàn bộ JVM option**:

```bash
java "-XX:DumpLoadedClassList=out dir/app.classlist" \
     -cp app.jar demo.App
```

Các ví dụ này giả định đã có JAR và thư mục phù hợp. Vị trí thực của file được quyết định theo quy tắc path của hệ điều hành/JVM.

## 5. Một chương trình Java 17+ để quan sát class loading

Tạo file **`src/demo/App.java`** với nội dung:

```java
package demo;

import java.util.List;

public final class App {
    public static void main(String[] args) {
        var values = List.of("one", "two", "three");
        int total = values.stream().mapToInt(String::length).sum();

        System.out.println("READY total=" + total);
        System.out.println("HELPER=" + Helper.name());
    }
}

final class Helper {
    static String name() {
        return "demo";
    }
}
```

Giải thích:

- `package demo;` xác định binary name `demo.App` và `demo.Helper`.
- `List.of(...)` và stream API tạo một workload nhỏ, có sử dụng một số lớp thư viện Java.
- `Helper.name()` khiến lớp `demo.Helper` được dùng thực sự.
- Cả hai lớp ở cùng source file; chỉ `App` là `public`, đúng yêu cầu đặt tên file `App.java`.
- Chương trình in output xác định, không phụ thuộc thời gian, mạng, file ngoài hoặc locale mặc định.

Khi chạy bình thường, stdout chính xác:

```text
READY total=11
HELPER=demo
```

Tổng `11` là độ dài `"one"` (3), `"two"` (3), `"three"` (5). Hai dòng này cũng xuất hiện khi chương trình chạy ở bước thu class list và khi được nạp từ static archive.

### Cấu trúc thư mục demo

```text
demo-work/
└── src/
    └── demo/
        └── App.java
```

Trong các lệnh dưới đây, đứng ở thư mục `demo-work`. Không tạo hoặc sửa file dự án khác chỉ để chạy ví dụ; có thể tạo một thư mục làm việc tạm nếu muốn thực hành an toàn.

## 6. Biên dịch và đóng gói JAR

Sử dụng JDK 17+ để biên dịch chương trình:

```bash
javac --release 17 -encoding UTF-8 \
      -d classes src/demo/App.java
jar --create --file app.jar -C classes .
```

Với terminal PowerShell, hai lệnh có thể viết một dòng mỗi lệnh, không cần dấu `\` nối dòng:

```powershell
javac --release 17 -encoding UTF-8 -d classes src/demo/App.java
jar --create --file app.jar -C classes .
```

Vì sao cần tạo JAR?

Theo hướng dẫn Oracle Java 26 cho **static CDS archive** với quy trình thu class list này, classpath dùng trong ví dụ chỉ chứa **JAR files**. Sử dụng `-cp classes` trỏ tới thư mục chứa các `.class` không phải mẫu áp dụng an toàn để tạo static archive bao gồm application classes: các **non-empty classpath directories** có thể làm bước tạo archive thất bại hoặc vô hiệu hóa khả năng archiving một số lớp.

Với JAR:

```bash
java -cp app.jar demo.App
```

Kết quả:

```text
READY total=11
HELPER=demo
```

**Điều kiện kiểm thử:** `app.jar` phải tồn tại, chứa `demo/App.class` và `demo/Helper.class`. Nếu mã biên dịch lỗi hoặc tên package/main class khác, cần sửa trước khi thử AppCDS.

### Vì sao dùng `--release 17`?

`--release 17` cho phép minh họa việc biên dịch tương thích API/bytecode của Java 17. Nhưng việc bật CDS là tính năng của **runtime JVM khi chạy**, không phải do `--release 17` bật lên.

Biên dịch bằng `--release 17` không đảm bảo có thể dùng archive tạo từ một JDK khác phiên bản. Archive phải tương thích với **JDK và môi trường** đang dùng để nạp nó.

## 7. Thu class list bằng một training run

Với `app.jar` đã có:

```bash
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
     -cp app.jar demo.App
```

Ứng dụng chạy và in:

```text
READY total=11
HELPER=demo
```

Sau khi chương trình kết thúc bình thường, kiểm tra file `app.classlist`. JVM dùng thông tin của những lớp đã thực sự được nạp trong quá trình chạy.

**Không đồng nhất training run với một lượt scan toàn bộ JAR:** JVM không mặc định nạp tất cả lớp trong thư viện. Một lớp nằm trong JAR nhưng chưa được sử dụng trên đường chạy ấy có thể **không xuất hiện** trong danh sách thu thập được.

### Vì sao training cần đại diện cho production?

Nếu ứng dụng có nhiều nhánh:

- Khởi động server và khởi tạo dependency injection.
- Endpoint tạo báo cáo, ghi log, xử lý JSON.
- Tải plugin hoặc tính năng tùy chọn.
- Các nhánh lazy-loading chỉ chạy sau request đầu tiên.

thì training run chỉ tải được các lớp của những nhánh thực sự được kích hoạt. Nếu bạn kết thúc ngay sau dòng “server started” mà chưa có request đại diện, danh sách sẽ thiên về quá trình bootstrap.

**Thiết kế training đúng:**

1. Dùng cùng artifact ứng dụng và cùng môi trường JVM tương thích với deployment.
2. Chạy các luồng khởi động và use case tiêu biểu.
3. Cho ứng dụng kết thúc có kiểm soát để JVM hoàn tất quá trình ghi class list.
4. Kiểm tra file kết quả và thông báo lỗi của JVM.
5. Gắn version của artifact/JDK/cấu hình với class list để tránh dùng nhầm trong build sau.

Đừng cố tải mọi class của JDK hoặc mọi class có trong classpath để làm danh sách “đủ nhất”: class list quá lớn có thể tạo archive tốn dung lượng, tăng thời gian tạo và không đem lại lợi ích tương xứng.

## 8. Đọc classlist: những gì nhìn thấy và những gì không nên giả định

Trong file được sinh ra, các binary class names thường dùng dạng nội bộ với dấu `/` thay vì dấu chấm `.`:

```text
java/lang/Object
java/lang/String
...
demo/App
demo/Helper
...
```

Đây là **minh họa rút gọn**, không phải file classlist đầy đủ hay output bất biến. File thật có thể chứa thông tin metadata phụ thuộc version JDK, class loader, nguồn JAR, ID và các bản ghi hỗ trợ cho các lớp khác.

**Đừng tự sửa một file classlist sinh bởi JVM như file văn bản thông thường nếu không hiểu format mà JVM đang dùng**. Không tự xóa metadata hoặc thay tên lớp `demo/App` thành `demo.App`: đó có thể làm archive creation lỗi.

### Kiểm tra nhanh trên Linux/macOS

```bash
test -s app.classlist
grep -E '^demo/(App|Helper)([[:space:]]|$)' app.classlist
```

`test -s` kiểm tra file không rỗng; `grep` tìm những dòng có tên các lớp demo. Kết quả `grep` có thể kèm metadata khác trên cùng dòng, nên **không hardcode toàn bộ dòng**.

### Kiểm tra nhanh trong PowerShell

```powershell
Test-Path .\app.classlist
(Get-Item .\app.classlist).Length
Select-String -Path .\app.classlist -Pattern '^demo/(App|Helper)(\s|$)'
```

Các lệnh trên là thao tác **đọc** file sinh ra; `Test-Path` chỉ nói file tồn tại, còn `Length` giúp biết file có dữ liệu. `Select-String` tìm class name mà không phải đoán tất cả lớp được nạp.

### Không assert số dòng classlist cố định

Ngay cả với cùng chương trình, số lớp được load có thể thay đổi theo:

- JDK build và class libraries.
- Class loader và module configuration.
- Workload, runtime flags, framework version.
- Lazy initialization, logging, instrumentation, code paths.
- Khác biệt giữa training run và production.

Test tốt xác nhận:

- File class list được tạo và không rỗng.
- Có một số application classes biết chắc đã được dùng.
- Các bước tạo và nạp archive hoạt động.
- Hành vi ứng dụng không thay đổi.

Đừng viết unit test yêu cầu “classlist phải có đúng 1.486 dòng” hoặc “mọi file `.class` trong JAR đều xuất hiện”.

## 9. Bước tiếp theo: tạo static CDS archive từ class list

Sau khi `app.classlist` tồn tại:

```bash
java -Xshare:dump \
     -XX:SharedArchiveFile=app.jsa \
     -XX:SharedClassListFile=app.classlist \
     -cp app.jar
```

Đây là **lệnh dump**, không phải lệnh chạy `demo.App.main`. JVM đọc danh sách và tạo một **static CDS archive**.

Phân biệt flag:

| Flag | Vai trò |
| --- | --- |
| `-XX:DumpLoadedClassList=...` | **Ghi classlist** khi chạy ứng dụng |
| `-XX:SharedClassListFile=...` | **Đọc classlist** để tạo archive |
| `-XX:SharedArchiveFile=...` | Xác định đường dẫn archive `.jsa` |
| `-Xshare:dump` | Chế độ JVM **tạo** CDS archive |
| `-Xshare:on` | Bật CDS và yêu cầu archive dùng được; hữu ích cho QA |
| `-Xshare:off` | Tắt CDS, thường dùng lúc thu class list trong workflow được tài liệu hóa |

**Sai lầm rất phổ biến:** chạy:

```bash
java -Xshare:dump -XX:DumpLoadedClassList=app.classlist \
     -XX:SharedArchiveFile=app.jsa -cp app.jar
```

rồi mong `DumpLoadedClassList` là tùy chọn đọc danh sách. Không đúng; **đầu vào của bước dump là `SharedClassListFile`**.

### Tính tương thích của archive

Oracle nhấn mạnh:

- Classpath/module path phải tương thích giữa lúc tạo và lúc dùng; với static archive, classpath ở thời điểm tạo phải là **cùng classpath hoặc tiền tố phù hợp** của classpath thời điểm chạy theo các hạn chế trong tài liệu.
- Các JAR dùng để tạo archive **không được sửa** sau đó rồi mong archive cũ nạp như bình thường.
- JDK build và các tùy chọn VM phải phù hợp; không copy archive qua các bản phát hành/JDK build khác nhau rồi kỳ vọng JVM sẽ dùng.
- Một số module/classloader arrangements hoặc JVMTI instrumentation có thể làm lớp không được archived hoặc làm archive không dùng được.

Nên xem `app.classlist` và `app.jsa` là **artifact gắn với bản build và môi trường**, không phải resource chung được chia sẻ tùy ý qua các phiên bản ứng dụng.

### Static archive không nhất thiết chứa tất cả class trong classlist

Có các hạn chế của CDS liên quan array classes, classloader, nguồn JAR và tính hợp lệ của metadata. Một class được quan sát trong training không phải **lời hứa** rằng nó sẽ được archived. Phải kiểm bằng log khi chạy lại.

## 10. Chạy lại ứng dụng với archive

```bash
java -XX:SharedArchiveFile=app.jsa -cp app.jar demo.App
```

Stdout nghiệp vụ vẫn là:

```text
READY total=11
HELPER=demo
```

Mục tiêu CDS là cải thiện hành vi vận hành như startup/memory, **không thay đổi kết quả của hàm `main`**.

### Bật chế độ chẩn đoán nghiêm ngặt

```bash
java -Xshare:on -XX:SharedArchiveFile=app.jsa \
     -cp app.jar demo.App
```

`-Xshare:on` hữu ích khi kiểm thử vì JVM có thể báo lỗi nếu archive không dùng được, thay vì âm thầm chạy theo lối khác. Tuy nhiên ở sản phẩm thực tế, quyết định fail-fast hoặc fallback cần dựa vào chính sách vận hành. Không tự áp dụng `-Xshare:on` vào mọi deployment khi thiếu archive không phải lỗi khiến ứng dụng phải dừng.

### Xác nhận có lớp nạp từ shared archive

```bash
java -Xshare:on -XX:SharedArchiveFile=app.jsa \
     -Xlog:class+load=info \
     -cp app.jar demo.App
```

Bạn sẽ thấy nhiều dòng log class loading. Khi một lớp demo được sử dụng từ archive, log có thể chứa dòng với ý nghĩa như:

```text
[...][info][class,load] demo.App source: shared objects file
[...][info][class,load] demo.Helper source: shared objects file
```

**Đây là trích đoạn minh họa**: timestamp, tag formatting và các dòng log khác thay đổi theo runtime. Vì vậy test nên tìm **chuỗi nhận diện lớp và nguồn** thay vì so toàn bộ log byte-by-byte.

Chú ý phân biệt:

- **Có dòng trong `app.classlist`** → lớp được quan sát trong training.
- **Có file `app.jsa`** → archive đã được tạo.
- **Có `source: shared objects file` cho lớp liên quan** → chứng cứ runtime đang nạp lớp đó từ shared archive.

Một test chỉ kiểm `app.jsa` tồn tại chưa đủ chứng minh ứng dụng production thực sự đang dùng nó.

## 11. Lệnh nguyên chu trình dành cho Linux/macOS

Giả sử bạn đã tạo `src/demo/App.java` và đang ở thư mục demo:

```bash
# 1. Biên dịch
javac --release 17 -encoding UTF-8 -d classes src/demo/App.java

# 2. Đóng gói
jar --create --file app.jar -C classes .

# 3. Kiểm output nghiệp vụ
java -cp app.jar demo.App

# 4. Chạy training và thu class list
java -Xshare:off -XX:DumpLoadedClassList=app.classlist \
     -cp app.jar demo.App

# 5. Kiểm file đã sinh
test -s app.classlist
grep -E '^demo/(App|Helper)([[:space:]]|$)' app.classlist

# 6. Tạo static archive
java -Xshare:dump -XX:SharedArchiveFile=app.jsa \
     -XX:SharedClassListFile=app.classlist -cp app.jar

# 7. Yêu cầu sử dụng archive, đồng thời log class loading
java -Xshare:on -XX:SharedArchiveFile=app.jsa \
     -Xlog:class+load=info -cp app.jar demo.App
```

Các lệnh trên minh họa **tác vụ đọc/ghi file build trong một thư mục demo riêng**. Không phải lệnh để thực hiện trong root của một dự án đang triển khai nếu chưa phân biệt rõ artifact và quyền ghi.

### Điều không nên làm

Đừng đổi version JDK giữa bước 4, 6 và 7 mà vẫn giữ archive cũ; đừng thay nội dung `app.jar` rồi chỉ chạy lại bước 7; đừng thu classlist bằng một classpath và tạo archive bằng classpath hoàn toàn khác.

## 12. Lệnh tương đương trong Windows PowerShell

PowerShell không dùng dấu `\` cuối dòng để nối các lệnh. Có thể gõ từng dòng:

```powershell
javac --release 17 -encoding UTF-8 -d classes src/demo/App.java
jar --create --file app.jar -C classes .

java -cp app.jar demo.App

java -Xshare:off -XX:DumpLoadedClassList=app.classlist -cp app.jar demo.App

Test-Path .\app.classlist
(Get-Item .\app.classlist).Length
Select-String -Path .\app.classlist -Pattern '^demo/(App|Helper)(\s|$)'

java -Xshare:dump -XX:SharedArchiveFile=app.jsa -XX:SharedClassListFile=app.classlist -cp app.jar

java -Xshare:on -XX:SharedArchiveFile=app.jsa -Xlog:class+load=info -cp app.jar demo.App
```

Khi chạy từ working directory chứa JAR và classlist, các tên file tương đối nêu trên phải trỏ đúng file đã tạo.

**Cảnh báo về Windows:** nếu một flag `-XX:...=<path>` chứa dấu cách, quote nguyên JVM argument bằng `"..."`. Nếu cần dùng nhiều archive trong `-XX:SharedArchiveFile`, delimiter Windows là dấu `;`, trong khi Unix-like dùng `:` — không dùng dấu phân cách classpath/archives của hệ khác.

## 13. Một chương trình Java hoàn chỉnh không tự “thu classlist”

Tệp `App.java` ở mục 5 chỉ thực hiện nghiệp vụ. Nó **không** gọi Java API nào để tự tạo classlist:

```java
System.out.println("READY total=" + total);
System.out.println("HELPER=" + Helper.name());
```

Đây là thiết kế đúng: việc thu classlist nằm ở **JVM launch command**, không nằm trong mã nghiệp vụ.

Không viết class có tên `DumpLoadedClassList` hoặc tìm phương thức `ClassLoader.dumpLoadedClassList()` trong Java standard API; flag này là **tùy chọn của HotSpot JVM launcher**.

### Khi cần thu lớp mà không sửa mã ứng dụng

Bạn thường chỉ cần thêm flag vào startup command ở môi trường training, chẳng hạn file cấu hình container hoặc script chạy test. **Đừng bật mặc định flag thu classlist ở mọi phiên production** nếu không thực sự cần tạo file liên tục: nó là một nhiệm vụ quan sát/phân tích riêng, có chi phí và tác động I/O.

Nếu muốn xác định lớp được nạp **trong một lần chạy đang diễn ra**, `-Xlog:class+load=info` có thể hỗ trợ chẩn đoán, nhưng log **khác định dạng và mục đích** với classlist mà `SharedClassListFile` nhận làm đầu vào cho dump.

## 14. Chọn workload training đại diện: ghi lại lớp nào mới có ích?

Giả sử một service có ba nhóm lớp:

- `BootstrapConfig` và các class khởi động container.
- `HttpHandler` và JSON serializers chỉ hoạt động khi có request.
- `ReportEngine` chỉ chạy khi người dùng yêu cầu tạo báo cáo.

Nếu training run chỉ khởi động rồi thoát, `ReportEngine` có thể không vào classlist. Điều đó **không có nghĩa JVM không hỗ trợ AppCDS cho class ấy**, mà do workload chưa làm nó được nạp.

Một quy trình thử nghiệm hợp lý:

1. Xác định **khối lượng công việc đại diện**: khởi động + request điển hình.
2. Chạy integration test sử dụng các code paths thực tế.
3. Thu danh sách lớp từ process JVM training.
4. Kiểm có các class quan trọng đã được quan sát.
5. Tạo archive và chạy lại với cùng artifact/cấu hình tương thích.
6. Đo cold/warm startup và memory.
7. Nếu thiếu lợi ích, xem classlist, log archive, path, class loader và độ đại diện của training.

**Lưu ý:** nhồi một loạt workload không bao giờ xuất hiện lúc startup vào archive có thể tăng kích thước mà không tạo lợi ích thực tế cho thời gian khởi động. Tối ưu phải dựa trên hành vi ứng dụng được đo, không dựa trên “càng nhiều class trong file càng tốt”.

## 15. Khác biệt giữa classlist và số liệu class loading log

Một classlist giúp **tạo archive**. Ngược lại, `-Xlog:class+load=info` giúp quan sát lớp được nạp và nguồn của chúng khi JVM chạy:

```bash
java -Xlog:class+load=info -cp app.jar demo.App
```

Trong log thông thường, lớp có thể có nguồn JAR hoặc runtime image, ví dụ:

```text
[...][info][class,load] demo.App source: file:/.../app.jar
```

Khi dùng archive, cùng lớp có thể đến từ:

```text
[...][info][class,load] demo.App source: shared objects file
```

Không dùng output của `-Xlog:class+load` thay cho `app.classlist` ở `SharedClassListFile`: hai file không tự tương thích. Tương tự, classlist không phải báo cáo đo thời gian startup và không cho biết một lớp **được nạp từ archive ở lần chạy nào**.

### Với logging lớn

Một lần chạy có thể in hàng nghìn dòng class loading. Nếu cần lưu log:

```bash
java -Xshare:on -XX:SharedArchiveFile=app.jsa \
     -Xlog:class+load=info:file=class-loading.log \
     -cp app.jar demo.App
```

Tùy chọn Unified Logging cho phép ghi log vào file; output nghiệp vụ ở stdout có thể tiếp tục chỉ gồm hai dòng của chương trình. Trong thực tế cần quản lý dung lượng, quyền truy cập và retention của log chẩn đoán.

## 16. Lỗi và giới hạn thực tế

### 16.1. Không có file `app.classlist`

Kiểm các điều sau:

- Flag JVM đã đặt **trước** tên main class hoặc `-jar` chưa?
- Thư mục chứa file có tồn tại và writable không?
- Ứng dụng có thật sự được khởi chạy và thoát một cách phù hợp không?
- Có process bị kill/cảnh báo JVM làm file chưa hoàn tất không?
- Đường dẫn tương đối có đang được hiểu theo working directory khác không?
- JVM hiện tại có hỗ trợ flag không?

**Không kết luận** “không có classlist nghĩa là không có class nào được nạp” — gần như chắc chắn ứng dụng đã phải nạp class để chạy; lỗi nằm ở quy trình thu thập, path hoặc runtime.

### 16.2. Classlist không có lớp mong đợi

Có thể vì:

- Lớp chưa được dùng trong workload.
- Feature được lazy-load.
- Custom class loader có cơ chế đặc biệt.
- Điều kiện cấu hình, reflection, plugin hoặc các nhánh ứng dụng chưa được kích hoạt.
- Một số loại class không được biểu diễn/archived theo cách bạn tưởng.

**Không giải quyết bằng cách giả định mọi class trong JAR phải hiện diện.** Thay vào đó làm training phù hợp và quan sát đường chạy có thật.

### 16.3. Tạo archive `.jsa` lỗi

Nguyên nhân phổ biến:

- `-XX:SharedClassListFile` trỏ sai file.
- File classlist được tạo từ JDK không tương thích.
- Classpath chứa thư mục không rỗng trong trường hợp bị giới hạn.
- JAR đã thay đổi hoặc không còn tồn tại.
- Đường dẫn archive không ghi được.
- JVM option hoặc môi trường khác thời điểm training.

Đọc **lỗi thật của JVM** thay vì xóa những dòng classlist không hiểu rồi thử lại; classlist chứa metadata mà JVM dùng để tạo archive.

### 16.4. Archive tồn tại nhưng ứng dụng vẫn tải lớp từ JAR

Có thể archive không hợp lệ hoặc được bỏ qua, một số lớp không đủ điều kiện archiving, path/flags không khớp, hoặc một classloader của framework tạo bản class khác.

**Cách kiểm:** bật `-Xshare:on` trong môi trường QA, xem thông báo JVM; dùng `-Xlog:class+load=info` để xác nhận **chính lớp** muốn tối ưu có nguồn `shared objects file`.

### 16.5. Thay JAR sau khi dump

Không coi `app.jsa` là artifact độc lập với `app.jar`. Nội dung JAR đổi làm archive cũ không còn tương thích theo hợp đồng của CDS. Xây dựng lại classlist/archive sau mỗi thay đổi liên quan bytecode/classpath/JDK.

### 16.6. Hiệu năng không cải thiện

CDS tối ưu một phần chi phí class loading, metadata và memory sharing. Ứng dụng có thể bị chi phối bởi:

- Network/database latency.
- Class initialization và DI framework.
- I/O config và authentication.
- JIT compilation và application warmup.
- Khởi động container, DNS, disk cache.

Nếu những yếu tố khác chiếm đa số, việc có thêm shared classes **không đảm bảo** startup giảm rõ rệt. Đo với benchmark thích hợp, thay vì gọi classlist “càng lớn càng nhanh”.

## 17. Những hạn chế về classpath, module path và class loader

Tài liệu `java` launcher JDK 26 mô tả những ràng buộc của CDS archive:

- **Classpath và module path không được chứa non-empty directories** trong workflow archive tương ứng, nếu phạm vi đó bị hạn chế.
- Với module path, chỉ **modular JARs** được hỗ trợ; exploded modules có giới hạn.
- Classpath của lúc tạo archive phải tương thích với lúc chạy; một thay đổi JAR hoặc thứ tự classpath có thể dẫn tới không dùng hoặc dùng không đầy đủ.
- Một số tùy chọn như `--patch-module`, `--upgrade-module-path`, `--limit-modules` có thể làm CDS bị vô hiệu hóa hoặc dump báo lỗi.
- Các lớp nạp qua custom class loaders, generated bytecode hoặc tác nhân biến đổi bytecode cần kiểm tương thích thực tế; không suy luận tất cả sẽ được lưu archive.
- Khi tích hợp frameworks, cần theo hướng dẫn của framework/bản phân phối JDK cho packaging và class loading.

**Không hardcode “thêm flag là chạy với mọi fat JAR”.** Nhiều executable/nested JAR packaging có class loader và cấu trúc path riêng; quy trình ví dụ `-cp app.jar demo.App` được cố ý đơn giản hóa và phù hợp để học cơ chế gốc.

Nếu bạn cần AppCDS cho Spring Boot hoặc framework khác, hãy kiểm đường dẫn JAR thực được JVM nhìn thấy, dạng exploded/extracted archive mà framework hỗ trợ và tài liệu hiện hành của framework đó.

## 18. Các lựa chọn CDS hiện đại không cần tự thu class list

Flag `-XX:DumpLoadedClassList` **vẫn tồn tại**, nhưng không phải lúc nào cũng đáng tự làm ba bước. Các lựa chọn hiện hành:

### 18.1. Dynamic archive với `-XX:ArchiveClassesAtExit`

Trong một số JDK HotSpot hiện đại:

```bash
java -XX:ArchiveClassesAtExit=app-dynamic.jsa -cp app.jar demo.App
```

JVM thực thi chương trình và có thể sinh **dynamic CDS archive** khi tiến trình thoát, không cần bạn tự chuẩn bị `app.classlist` và `-Xshare:dump`.

Sử dụng:

```bash
java -XX:SharedArchiveFile=app-dynamic.jsa -cp app.jar demo.App
```

Đây là workflow khác; không tráo `app-dynamic.jsa` với file text `app.classlist`. Dynamic archive thường được tạo trên nền static archive tương thích và có những giới hạn/ưu điểm riêng.

### 18.2. Tạo archive bằng `jcmd VM.cds`

Trong một số tình huống khó chỉnh startup script, công cụ `jcmd` có thể yêu cầu JVM đang chạy dump archive:

```bash
jcmd <pid> VM.cds static_dump app-static.jsa
```

Đây là cú pháp minh họa: `<pid>` cần thay bằng process ID thực, không gõ nguyên. Tùy loại dump, JVM có các điều kiện/flag bổ sung, đặc biệt dynamic dump. Cách này phù hợp khi muốn kết nối tới process đang chạy; không phải cơ chế thay thế trực tiếp cho `-XX:DumpLoadedClassList` trong mọi trường hợp.

### 18.3. Auto-create shared archive trên JDK hỗ trợ

Các bản JDK hiện đại như JDK 26 còn tài liệu hóa:

```bash
java -XX:+AutoCreateSharedArchive \
     -XX:SharedArchiveFile=app-auto.jsa \
     -cp app.jar demo.App
```

Tùy chọn này hướng tới việc quản lý archive tiện hơn và không yêu cầu một lượt tạo classlist thủ công, nhưng có quy tắc về archive hiện có, JDK build và cách cập nhật. Chỉ dùng khi runtime cụ thể hỗ trợ và đã đọc hợp đồng của phiên bản triển khai.

**Cách chọn:** đối với một bài thực hành chuyên đề “thu class list”, hiểu `DumpLoadedClassList` là thiết yếu. Đối với một dự án mới, hãy đánh giá cách tạo CDS archive tự động/dynamic hoặc AOT cache tùy JDK và mục tiêu hiệu năng.

## 19. AOT cache JDK 25+: giải pháp mới đáng cân nhắc

Trên JDK 25/26, **Ahead-of-Time (AOT) cache** được tài liệu hóa với cách dùng:

```bash
# Chỉ chạy khi đang dùng JDK hỗ trợ -XX:AOTCacheOutput (JDK 25+)
java -XX:AOTCacheOutput=app.aot -cp app.jar demo.App

# Dùng cache sau khi tạo thành công
java -XX:AOTCache=app.aot -cp app.jar demo.App
```

Các lệnh này là **ví dụ cho JDK 25+**, **không thuộc quy trình đã kiểm thử trên JDK 24**. Flag `-XX:AOTCacheOutput` có thể báo `Unrecognized VM option` trên JDK 24, dù AOT caching đã bắt đầu được triển khai theo các JEP liên quan từ JDK 24. Hãy đối chiếu tài liệu chính xác của phiên bản runtime.

### Vì sao AOT cache có thể phù hợp hơn?

Theo tài liệu JDK 26, cache AOT có thể chứa những artifact tối ưu hóa khác bên cạnh class metadata và được thiết kế cho luồng **training → assembly → production**. Static CDS là một cơ chế trước đó vẫn được hỗ trợ, nhưng không bao quát mọi tối ưu mà AOT cache mới có thể cung cấp.

**Ràng buộc triển khai:**

- AOT cache phụ thuộc JDK release/build, cấu hình application classpath/JAR và hệ điều hành/kiến trúc theo mức hỗ trợ.
- Training phải đủ đại diện, có tùy chọn JVM phù hợp với production.
- Khi ứng dụng/JDK hoặc môi trường đổi, xây lại cache theo hướng dẫn.
- Dùng `-Xlog:aot` và chế độ phù hợp khi chẩn đoán liệu cache đã được dùng.
- Nếu runtime không có `AOTCacheOutput`, **không gắn cứng flag này**; sử dụng cơ chế CDS tương thích hoặc nâng JDK có kiểm soát.

**Không nhầm `app.aot` với `app.classlist` hoặc `app.jsa`**: chúng không có cùng định dạng và không thể dùng thay tên file cho nhau.

### Một bảng chọn nhanh

| Hoàn cảnh | Cách nên cân nhắc |
| --- | --- |
| Cần học cơ chế thu classes bằng flag được giao | `-XX:DumpLoadedClassList` rồi static CDS |
| Cần debug chính xác classlist được ghi | `DumpLoadedClassList` + kiểm nội dung |
| Cần tạo CDS archive không giữ classlist trung gian | `-XX:ArchiveClassesAtExit` nếu được hỗ trợ |
| Cần dump archive từ process đang chạy | `jcmd VM.cds` trên JDK và cấu hình phù hợp |
| Triển khai trên JDK 25/26 mới, muốn AOT tối ưu hơn | AOT cache `-XX:AOTCacheOutput` / `-XX:AOTCache` |
| Chỉ cần ứng dụng chạy, chưa đo thấy lợi ích | Có thể dùng CDS mặc định của JDK, đo trước khi tùy biến |

## 20. Bảo mật, quyền file và tái tạo artifact

Class list/archive là **artifact vận hành**, có thể chứa thông tin về:

- Class names và cấu trúc package của ứng dụng.
- Đường dẫn/source JAR và metadata liên quan đến class loader.
- Những module hoặc tính năng đã được chạm tới trong training.

Không nên xuất bản công khai các file này nếu chúng tiết lộ cấu trúc hệ thống nội bộ. Giới hạn quyền đọc/ghi phù hợp với thư mục build và phân phối artifact thông qua pipeline đáng tin cậy.

Với file archive `.jsa`:

- **Không cho nguồn không tin cậy sửa file archive** rồi để production nạp nó.
- Dùng chính sách quyền tệp, checksum và integrity của artifact pipeline khi cần.
- Đặt archive và JAR trong khu vực phiên bản hóa, gắn với JDK build và commit/bản release liên quan.
- Xóa classlist/archive tạm khi không còn dùng để tránh nhầm và lãng phí dung lượng.

Tài liệu `java` còn có các tùy chọn kiểm tra integrity như `-XX:+VerifySharedSpaces`, nhưng điều đó **không thay thế** cơ chế quản lý nguồn artifact tin cậy, quyền ghi hoặc kiểm soát cung ứng phần mềm.

## 21. Cách đo hiệu quả AppCDS chính xác

Để biết AppCDS có giúp sản phẩm hay không, cần xác định chỉ số cụ thể:

1. **Startup latency**: thời gian từ khi gọi JVM đến khi ứng dụng sẵn sàng.
2. **Memory footprint**: bộ nhớ thường trú, memory mapping/shared pages và tổng bộ nhớ của nhiều tiến trình.
3. **Warmup/throughput**: khi cần, đo riêng để tránh nhầm chi phí JIT hoặc load dữ liệu.
4. **Archive size** và thời gian xây archive: chi phí build/deploy.
5. **Tỷ lệ lớp liên quan thực sự nạp từ archive**: kiểm bằng Unified Logging.

Một thí nghiệm hợp lý:

- Dùng **cùng JDK build, classpath, config và workload** cho baseline và archive.
- Chạy đủ số lần để giảm nhiễu do disk cache, background processes hoặc JIT.
- Phân biệt **cold start** và **warm start**.
- Không cộng thời gian tạo `.jsa` vào thời gian startup production, nhưng phải cân nhắc trong tổng chi phí pipeline.
- Quan sát cả số đo phân phối (median/p95) thay vì chỉ một lần nhanh nhất.
- Nếu muốn đo memory sharing giữa nhiều JVM, đo nhiều tiến trình đồng thời thay vì chỉ heap của một JVM.

`-XX:DumpLoadedClassList` **không phải flag đo hiệu năng**. Nó là bước thu class metadata cho workflow static archive; bật flag trong baseline đo startup có thể thêm overhead và khiến phép so sánh không công bằng.

## 22. Troubleshooting theo triệu chứng

| Triệu chứng | Cần kiểm |
| --- | --- |
| `Unrecognized VM option DumpLoadedClassList` | Loại JVM, phiên bản, hỗ trợ HotSpot CDS |
| Không thấy `app.classlist` | Vị trí working directory, quyền, quá trình kết thúc, đặt flag trước main |
| `app.classlist` rỗng | JVM/training có lỗi? Đọc stderr và trạng thái process |
| Không thấy `demo/App` | Main class đã chạy đúng JAR? File tạo từ đúng training run? |
| Classlist có nhiều dòng không quen | Bình thường: có lớp JDK và dependency đã nạp; không hardcode số dòng |
| `-Xshare:dump` báo lỗi classpath | JAR/path, non-empty directories, module flags, metadata classlist |
| Tệp `app.jsa` không xuất hiện | Có dùng `SharedClassListFile` và quyền ghi archive? Dump exit code? |
| JVM dùng JAR chứ không dùng `shared objects file` | Archive có nạp không, class có được archive không, JAR có đổi không |
| Chạy `-Xshare:off` ở production nhưng không thấy lợi ích | `-Xshare:off` đã tắt CDS, bỏ flag này ở bước sử dụng |
| Sau nâng cấp JDK ứng dụng bỏ qua archive | Archive/JDK build khác; cần tạo lại |
| Fat JAR/framework class loader khác demo | Kiểm tài liệu framework và đóng gói runtime thực tế |
| Startup không nhanh hơn | Workload thiếu lớp cần thiết, archive không nạp, bottleneck ngoài class loading |
| `-XX:AOTCacheOutput` không được nhận trên JDK 24 | Flag này dành cho JDK 25+, không nằm trong workflow AppCDS thủ công |

## 23. Bài tập thực hành và tự kiểm tra

**Câu 1.** `-XX:DumpLoadedClassList=app.classlist` sinh ra tệp loại gì? Có tự tạo `app.jsa` không?

**Câu 2.** Lệnh nào trong workflow này **đọc classlist** để tạo static archive?

**Câu 3.** Vì sao cần chạy ứng dụng với workload đại diện thay vì chỉ scan tất cả file `.class` trong JAR?

**Câu 4.** Dùng `-Xshare:off` trong bước thu list có nghĩa gì? Có nên giữ flag này khi chạy với archive không?

**Câu 5.** `app.classlist` có dòng `demo/App`; điều đó có chứng minh `demo.App` đã được nạp từ shared archive lúc production không?

**Câu 6.** Làm sao xác nhận một class được nạp từ archive?

**Câu 7.** Nếu classpath chứa thư mục `classes` không rỗng, có nên coi nó luôn hợp lệ cho quy trình static CDS trong ví dụ Oracle không?

**Câu 8.** Khi thay bytecode của `app.jar`, có nên sử dụng lại `app.jsa` cũ không?

**Câu 9.** Tại sao không nên assert classlist có đúng một số dòng cố định?

**Câu 10.** `-XX:+UseAppCDS` có nên thêm vào command trên JDK hiện đại không?

**Câu 11.** Lệnh nào giúp tạo dynamic archive mà không cần classlist trung gian, trên runtime hỗ trợ?

**Câu 12.** Phân biệt `-XX:SharedClassListFile` và `-XX:SharedArchiveFile`.

**Câu 13.** Vì sao `-XX:DumpLoadedClassList` không phải chỉ số benchmark startup?

**Câu 14.** Có nên dùng `-XX:AOTCacheOutput` trong JDK 24 không?

**Câu 15.** Lệnh `java -cp app.jar demo.App -XX:DumpLoadedClassList=...` có thu classlist đúng như mong muốn không?

**Câu 16.** Nếu `-Xlog:class+load=info` thấy `source: file:/.../app.jar`, có thể kết luận lớp ấy nạp từ shared archive không?

**Câu 17.** Khi test AppCDS, tại sao nên kiểm stderr/exit code của JVM thay vì chỉ kiểm file `.jsa` có tồn tại?

**Câu 18.** `-XX:DumpLoadedClassList` có ghi mọi lớp nằm trong app.jar không, kể cả lớp chưa bao giờ được nạp?

**Câu 19.** Archive tạo ở JDK 24 có thể sao chép nguyên trạng để dùng chắc chắn trên JDK 26 không?

**Câu 20.** Khi nào nên cân nhắc AOT cache JDK 25+ thay vì quy trình static CDS thủ công?

**Đáp án:**

1. Sinh **file class list văn bản**; không tự tạo `.jsa`.
2. `java -Xshare:dump -XX:SharedClassListFile=app.classlist -XX:SharedArchiveFile=app.jsa -cp app.jar`.
3. Vì danh sách nhằm phản ánh các lớp **thực sự được load** trong đường chạy; lớp không dùng có thể không xuất hiện.
4. Tắt CDS ở training để quan sát theo workflow được tài liệu hóa; **không giữ ở production** nếu muốn nạp archive.
5. Không; đó chỉ chứng minh class được quan sát trong training.
6. Dùng `-Xlog:class+load=info` và tìm `demo.App source: shared objects file` cùng log xác nhận archive.
7. Không; theo hạn chế của static CDS, nên đóng gói JAR như ví dụ.
8. Không; phải tạo lại archive phù hợp với bản ứng dụng mới.
9. Vì số lớp thay đổi theo JDK build, workload, framework và flags.
10. Không; flag đó obsolete trên JDK 11+ và không cần cho workflow này.
11. `-XX:ArchiveClassesAtExit=app-dynamic.jsa`.
12. `SharedClassListFile` là **đầu vào text**; `SharedArchiveFile` là **đường dẫn archive** dùng trong dump hoặc runtime.
13. Vì nó thu metadata và ghi file, có overhead; benchmark cần đo riêng baseline/production.
14. Không. `AOTCacheOutput` chưa có trên JDK 24; dùng JDK hỗ trợ như 25/26.
15. Không. Flag sau tên main class là đối số ứng dụng.
16. Không; đó là nguồn JAR, không phải shared archive.
17. Vì file có thể cũ/không hợp lệ hoặc dump thất bại một phần; cần xác nhận exit status và runtime loading.
18. Không; chỉ các lớp được load trong training.
19. Không; archive gắn với bản JDK/build, cấu hình và JAR.
20. Khi dùng JDK 25/26 và cần workflow AOT hiện đại với các artifact tối ưu hóa ngoài class metadata, theo tài liệu hiện hành.

## 24. Tổng kết và nguồn chính thức

**Ghi nhớ:**

- `-XX:DumpLoadedClassList=<file>` được dùng **khi chạy ứng dụng** để thu các lớp đã được JVM nạp.
- Tệp `.classlist` là **input cho bước tạo archive**; chưa phải CDS archive và không bảo đảm mọi class trong đó sẽ được archive.
- Luồng thủ công: **JAR → training/classlist → `-Xshare:dump`/`SharedClassListFile` → `.jsa` → nạp archive**.
- Chạy `-Xshare:on` và `-Xlog:class+load=info` để QA xem lớp có nạp từ `shared objects file` không.
- Kiểm tính tương thích của JDK, JAR, classpath và workload, xử lý các lỗi archiving đúng theo output JVM.
- Flag vẫn có mặt trong tài liệu JDK 26, nhưng **AOT cache trên JDK 25+** và những cơ chế tạo dynamic/auto CDS cũng đáng cân nhắc tùy nhu cầu.
- Không dùng `-XX:+UseAppCDS` (obsolete từ JDK 11) trong lệnh mới.
- Đo startup/memory bằng benchmark riêng, không đoán tốc độ từ số dòng class list.

**Nguồn chính thức và hiện hành:**

1. [Oracle Java SE 26 — The `java` Command / Application Class Data Sharing](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html#application-class-data-sharing): mô tả classlist, static archive, dynamic archive, logging, classpath restrictions và AOT cache.
2. [OpenJDK JEP 310 — Application Class-Data Sharing](https://openjdk.org/jeps/310): ngữ cảnh Java 10 và mục tiêu AppCDS.
3. [Oracle Java SE 26 — Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html#ahead-of-time-cache): `AOTCache`/`AOTCacheOutput` trên JDK hiện hành.
4. [OpenJDK JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): bối cảnh AOT cache và các điều kiện tương thích.
5. [OpenJDK JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): workflow AOT cache dễ dùng hơn trên JDK 25.
6. [Dev.java — The Java Launcher](https://dev.java/learn/jvm/tools/core/java/): giải thích flag `DumpLoadedClassList` và các flag AppCDS obsolete trên JDK mới.
