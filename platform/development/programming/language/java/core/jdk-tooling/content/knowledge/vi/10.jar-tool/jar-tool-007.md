# Thuộc tính Main-Class trong JAR

Một tệp JAR (Java Archive) có thể đóng gói các class file, tài nguyên và metadata của ứng dụng Java. Để chạy một ứng dụng từ JAR bằng lệnh `java -jar`, JVM cần biết lớp nào chứa điểm bắt đầu của chương trình. Thông tin này được khai báo bằng thuộc tính **`Main-Class`** trong manifest của JAR.

`Main-Class` cho Java launcher biết lớp cần khởi chạy. Giá trị của thuộc tính là tên lớp chính theo dạng tên nhị phân đầy đủ (fully qualified binary name), ví dụ `app.Main`; không phải đường dẫn tệp `.class`.

## 1. Manifest của JAR là gì?

Manifest là tệp metadata có tên:

```text
META-INF/MANIFEST.MF
```

Manifest nằm bên trong JAR và chứa các cặp thuộc tính dạng tên–giá trị. Nó có thể mô tả lớp khởi chạy, classpath phụ thuộc, thông tin phiên bản, nhà cung cấp và các metadata khác.

Một manifest tối thiểu thường có dạng:

```text
Manifest-Version: 1.0
Main-Class: app.Main

```

Ý nghĩa:

- `Manifest-Version: 1.0` xác định phiên bản định dạng manifest.
- `Main-Class: app.Main` chỉ định lớp có phương thức main mà Java launcher cần gọi.
- Dòng trống cuối cùng kết thúc phần main attributes của manifest.

Khi dùng `jar` để tạo JAR, công cụ có thể tự tạo manifest mặc định. Nếu chỉ định `--main-class`, công cụ ghi thuộc tính `Main-Class` phù hợp vào manifest.

**Lưu ý:** `Main-Class` phải nằm trong phần main attributes ở đầu manifest, trước dòng trống phân tách các named section. Đặt nó trong một named section không khai báo điểm bắt đầu mặc định cho toàn JAR.

## 2. Main-Class cần trỏ đến lớp nào?

Với ứng dụng Java thông thường trên classpath, lớp được khai báo trong `Main-Class` cần có phương thức main hợp lệ để Java launcher gọi.

Dạng phổ biến:

```java
public static void main(String[] args)
```

Ví dụ:

```java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from executable JAR");
    }
}
```

Vì lớp nằm trong package `app`, giá trị manifest phải là:

```text
Main-Class: app.Main
```

Các lưu ý quan trọng:

- Dùng tên lớp đầy đủ, có package nếu lớp thuộc package.
- Không thêm đuôi `.class`.
- Không thay dấu chấm phân cách package bằng dấu gạch chéo.
- Tên lớp phân biệt chữ hoa và chữ thường.
- Class file của lớp chính phải có trong JAR hoặc nằm ở vị trí được class loader tìm thấy.
- Phương thức main phải có chữ ký mà Java launcher hỗ trợ; ví dụ Java 17 dùng `public static void main(String[] args)`.

Ví dụ giá trị đúng là `app.Main`, không phải `app/Main.class`.

## 3. Tạo một executable JAR bằng tùy chọn --main-class

Giả sử dự án có cấu trúc:

```text
project/
  src/
    app/
      Main.java
```

Tạo tệp **`src/app/Main.java`**:

```java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from executable JAR");
    }
}
```

### Bước 1: Biên dịch mã nguồn

Chạy từ thư mục gốc `project`:

```bash
javac -d out src/app/Main.java
```

Sau khi biên dịch, class file nằm ở:

```text
out/
  app/
    Main.class
```

Thư mục `out` là gốc của cấu trúc package. Khi đóng gói, cần giữ đường dẫn `app/Main.class` bên trong JAR.

### Bước 2: Tạo JAR và khai báo Main-Class

Chạy:

```bash
jar --create --file app.jar --main-class app.Main -C out .
```

Giải thích:

- `--create`: tạo một JAR mới.
- `--file app.jar`: tên tệp JAR đầu ra.
- `--main-class app.Main`: ghi lớp khởi chạy vào manifest.
- `-C out .`: chuyển vào thư mục `out` rồi thêm nội dung của thư mục đó vào JAR.

Sau khi chạy, cấu trúc dự án:

```text
project/
  app.jar
  out/
    app/
      Main.class
  src/
    app/
      Main.java
```

Trong JAR, class file nằm ở đường dẫn `app/Main.class`; manifest nằm tại `META-INF/MANIFEST.MF`.

### Bước 3: Chạy JAR

Chạy:

```bash
java -jar app.jar
```

Kết quả:

```text
Hello from executable JAR
```

JAR được gọi là executable JAR vì Java launcher có thể tìm lớp khởi chạy thông qua manifest và chạy ứng dụng bằng `java -jar`.

Tên gọi này có nghĩa JAR có thể chạy bằng Java launcher; bản thân tệp JAR không nhất thiết là tệp thực thi native độc lập của hệ điều hành.

## 4. Tạo manifest thủ công

Ngoài `--main-class`, có thể tự tạo tệp manifest rồi truyền cho `jar`.

Tạo tệp **`MANIFEST.MF`** tại thư mục gốc dự án:

```text
Manifest-Version: 1.0
Main-Class: app.Main

```

Sau khi đã biên dịch lớp vào `out`, tạo JAR:

```bash
jar --create --file app.jar --manifest MANIFEST.MF -C out .
```

Chạy:

```bash
java -jar app.jar
```

Kết quả:

```text
Hello from executable JAR
```

Dùng manifest thủ công hữu ích khi cần khai báo thêm thuộc tính như `Class-Path`, thông tin phiên bản hoặc metadata tùy chỉnh.

Khi dùng manifest tự tạo, hãy bảo đảm:

- Tên tệp là `MANIFEST.MF` (không bắt buộc tên tệp nguồn phải như vậy, nhưng đây là quy ước dễ nhận biết).
- Các dòng có dạng `Tên-Thuộc-Tính: giá trị`.
- Có dòng trống để kết thúc main section.
- Không chèn khoảng trắng tùy ý trước tên thuộc tính.
- Nếu một dòng quá dài, tuân thủ quy tắc xuống dòng của manifest: dòng tiếp theo bắt đầu bằng một dấu cách; giới hạn được tính theo byte, không chỉ theo số ký tự.
- Với manifest có nội dung Unicode, lưu theo định dạng UTF-8 và tuân thủ quy tắc manifest của JAR.

Không đặt `Main-Class` sau dòng trống đầu tiên nếu muốn nó là điểm khởi chạy mặc định.

## 5. Kiểm tra Main-Class đã được ghi vào JAR

Sau khi tạo JAR, nên xác minh cả nội dung archive lẫn manifest.

### Liệt kê nội dung JAR

Chạy:

```bash
jar --list --file app.jar
```

Kết quả cần có các mục tương tự:

```text
META-INF/
META-INF/MANIFEST.MF
app/
app/Main.class
```

Thứ tự và một số mục hiển thị có thể khác theo phiên bản công cụ, nhưng cần có manifest và class file của lớp chính.

### Trích xuất manifest để xem

Có thể trích riêng manifest:

```bash
jar --extract --file app.jar META-INF/MANIFEST.MF
```

Sau đó đọc tệp vừa trích xuất:

**Windows PowerShell:**

```powershell
Get-Content META-INF/MANIFEST.MF
```

**macOS/Linux:**

```bash
cat META-INF/MANIFEST.MF
```

Nội dung cần có:

```text
Manifest-Version: 1.0
Created-By: ...
Main-Class: app.Main
```

Các thuộc tính bổ sung như `Created-By` phụ thuộc JDK. Điều cần xác minh là `Main-Class` có đúng tên lớp và nằm trong phần main attributes.

## 6. Truyền đối số cho chương trình khi chạy JAR

Các đối số ứng dụng được đặt sau tên JAR:

```bash
java -jar app.jar production 8080
```

Java launcher gọi phương thức main của lớp đã khai báo trong manifest. Trong phương thức:

- `args[0]` nhận `production`.
- `args[1]` nhận `8080`.
- `args.length` bằng 2.

Ví dụ:

```java
package app;

public class Main {
    public static void main(String[] args) {
        System.out.println("Argument count: " + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }
    }
}
```

Kết quả khi chạy `java -jar app.jar production 8080`:

```text
Argument count: 2
args[0]=production
args[1]=8080
```

Cần phân biệt đối số JVM với đối số ứng dụng:

```bash
java -Xmx512m -Dapp.mode=production -jar app.jar arg1 arg2
```

- `-Xmx512m` và `-Dapp.mode=production` là tùy chọn dành cho JVM, đặt trước `-jar`.
- `arg1` và `arg2` được chuyển vào `main(String[] args)`.

## 7. Main-Class và Class-Path trong manifest

Một ứng dụng có thể phụ thuộc vào các JAR bên ngoài. Manifest hỗ trợ thuộc tính `Class-Path` để khai báo các vị trí dependency cho Java launcher.

Ví dụ cấu trúc:

```text
project/
  app.jar
  lib/
    helper.jar
    logging.jar
```

Nội dung manifest:

```text
Manifest-Version: 1.0
Main-Class: app.Main
Class-Path: lib/helper.jar lib/logging.jar

```

Các mục trong `Class-Path` là URL, được phân cách bằng dấu cách. Đường dẫn tương đối được giải quyết tương đối với vị trí của JAR chứa manifest.

Tạo JAR bằng manifest:

```bash
jar --create --file app.jar --manifest MANIFEST.MF -C out .
```

Nếu các dependency nằm ở `lib/helper.jar` và `lib/logging.jar` tương đối với `app.jar`, hãy giữ cấu trúc thư mục đó khi triển khai.

Chạy:

```bash
java -jar app.jar
```

Java launcher sử dụng `Main-Class` làm entry point và đọc `Class-Path` để tìm dependency.

Lưu ý:

- `Class-Path` không tự đóng gói các JAR phụ thuộc vào bên trong `app.jar`; nó chỉ tham chiếu đến các vị trí bên ngoài.
- Các đường dẫn cần tồn tại tại thời điểm chạy và phải được phân giải đúng theo vị trí JAR.
- Mỗi mục là URL; nếu đường dẫn có ký tự đặc biệt hoặc khoảng trắng, cần mã hóa URL phù hợp.
- Không dùng dấu phân cách classpath của hệ điều hành (`;` hoặc `:`) trong giá trị manifest này; các URL được phân cách bằng dấu cách.
- Wildcard như `lib/*` không phải cách khai báo dependency chuẩn trong manifest `Class-Path`; liệt kê các JAR cụ thể.
- Không đưa bí mật hoặc thông tin xác thực vào manifest.

## 8. Khác biệt giữa java -jar và java -cp

Hai cách khởi chạy thường gặp có quy tắc khác nhau:

| Cách chạy | Lớp khởi chạy | Cách tìm dependency |
| --- | --- | --- |
| `java -cp "out:lib/*" app.Main` (macOS/Linux) | Tên lớp được ghi trên dòng lệnh | Classpath được truyền bằng `-cp` |
| `java -cp "out;lib/*" app.Main` (Windows) | Tên lớp được ghi trên dòng lệnh | Classpath được truyền bằng `-cp` |
| `java -jar app.jar` | Thuộc tính `Main-Class` trong manifest | JAR chính và các mục `Class-Path` trong manifest |

Khi dùng `java -jar`, các thiết lập classpath khác trên dòng lệnh hoặc biến môi trường `CLASSPATH` không được dùng để xác định classpath ứng dụng theo cách thông thường. Nếu ứng dụng cần JAR ngoài, hãy khai báo dependency trong manifest hoặc chọn cách khởi chạy bằng tên lớp với `-cp`.

Ví dụ, lệnh sau không phải cách bổ sung thư viện cho chế độ `-jar`:

```bash
java -cp lib/helper.jar -jar app.jar
```

Hãy đặt dependency vào manifest `Class-Path`, hoặc dùng cách chạy classpath:

```bash
java -cp "app.jar:lib/helper.jar" app.Main
```

Lệnh cuối dùng dấu hai chấm trên macOS/Linux. Trên Windows, thay dấu phân cách bằng dấu chấm phẩy.

## 9. Cập nhật Main-Class của JAR hiện có

Nếu đã có JAR và muốn thay đổi lớp khởi chạy, có thể cập nhật manifest bằng công cụ `jar`:

```bash
jar --update --file app.jar --main-class app.Main
```

Sau khi cập nhật, kiểm tra manifest và chạy lại:

```bash
jar --list --file app.jar
java -jar app.jar
```

Chỉ cập nhật JAR khi bạn có quyền sửa artifact đó và hiểu rõ lớp chính mới. Nếu JAR được tạo tự động trong pipeline build, nên sửa cấu hình build để lần đóng gói tiếp theo tạo ra manifest đúng thay vì sửa artifact thủ công sau mỗi lần build.

## 10. Lỗi thường gặp với Main-Class

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `no main manifest attribute` | Manifest không có thuộc tính `Main-Class` trong main section | Tạo lại JAR với `--main-class` hoặc manifest có `Main-Class` |
| `Could not find or load main class` | Giá trị `Main-Class` sai tên, sai package hoặc class không có trong JAR/classpath | Kiểm tra tên lớp và nội dung JAR bằng `jar --list` |
| `Main method not found` hoặc lỗi tương tự | Lớp được khai báo không có phương thức main hợp lệ cho launcher | Kiểm tra `public static void main(String[] args)` |
| Chạy được khi dùng `-cp` nhưng không chạy với `-jar` | Manifest thiếu dependency hoặc `Class-Path` sai | Kiểm tra manifest và vị trí các JAR phụ thuộc |
| Đã sửa manifest nhưng kết quả không đổi | JAR đang chạy không phải artifact vừa sửa hoặc manifest không được cập nhật đúng | Xác nhận đường dẫn JAR, liệt kê nội dung và đọc lại manifest |
| Không tìm thấy dependency có khoảng trắng trong tên | URL trong `Class-Path` chưa được mã hóa đúng | Dùng URL hợp lệ hoặc đặt dependency ở đường dẫn đơn giản |
| Lớp chính được tìm thấy nhưng báo lỗi khi nạp lớp khác | Thiếu dependency bắc cầu hoặc phiên bản thư viện không tương thích | Kiểm tra toàn bộ dependency runtime |

## 11. Thực hành tốt khi đóng gói executable JAR

- Dùng tên lớp đầy đủ và đúng chữ hoa/chữ thường trong `Main-Class`.
- Đảm bảo class file của entry point được đưa vào JAR.
- Ưu tiên `jar --main-class` khi chỉ cần khai báo lớp chính.
- Dùng manifest thủ công khi cần thêm `Class-Path` hoặc metadata.
- Kiểm tra manifest và danh sách file trước khi phát hành.
- Kiểm thử bằng chính lệnh `java -jar` trong môi trường triển khai.
- Giữ các dependency bên ngoài đúng vị trí nếu manifest tham chiếu đường dẫn tương đối.
- Dùng Maven hoặc Gradle để cấu hình manifest trong build tự động, giúp artifact tái lập.
- Phân biệt executable JAR thông thường với fat/uber JAR. Một JAR thông thường không tự chứa tất cả dependency nếu không đóng gói chúng.
- Không chỉnh sửa manifest trực tiếp sau khi ký số JAR; thay đổi nội dung archive có thể làm chữ ký không còn hợp lệ. Hãy tạo và ký lại artifact theo quy trình phát hành.

## 12. Ghi nhớ

- Manifest nằm tại `META-INF/MANIFEST.MF` bên trong JAR.
- `Main-Class` xác định lớp mà `java -jar` khởi chạy.
- Giá trị phải là tên lớp đầy đủ, ví dụ `app.Main`, không phải `app/Main.class`.
- Dùng `jar --create --file app.jar --main-class app.Main -C out .` để tạo executable JAR.
- Dùng `--manifest MANIFEST.MF` khi muốn tự khai báo các thuộc tính.
- `Class-Path` trong manifest tham chiếu các dependency ngoài JAR bằng URL tương đối hoặc tuyệt đối phù hợp.
- `java -jar` sử dụng manifest làm nguồn entry point và classpath ứng dụng; tùy chọn `-cp` không bổ sung classpath trong chế độ này.
- Luôn xác minh manifest và thử chạy JAR bằng Java launcher trước khi phát hành.

Khi hiểu thuộc tính `Main-Class`, bạn có thể đóng gói ứng dụng Java thành JAR có điểm khởi chạy rõ ràng, truyền đối số cho chương trình, quản lý dependency bên ngoài và chẩn đoán các lỗi thường gặp khi triển khai.
