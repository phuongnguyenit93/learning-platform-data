# Đăng ký nhà cung cấp trên classpath bằng META-INF/services (ServiceLoader)

## 1. Bài toán: cài thêm implementation mà không sửa mã gọi

Giả sử ứng dụng định nghĩa một giao diện `Greeter`. Lúc biên dịch ứng dụng, ta muốn mã gọi chỉ biết giao diện này; lúc chạy, các thư viện có thể cung cấp một hay nhiều lớp triển khai. Java có cơ chế Service Provider Interface (SPI) và `java.util.ServiceLoader` để tìm các implementation đáp ứng một service contract.

Khi provider được triển khai trên **classpath**, cách đăng ký chuẩn là đặt một **tệp tài nguyên** đúng tên trong thư mục `META-INF/services/`. Trong tệp, mỗi dòng chỉ định tên đầy đủ của một lớp triển khai. `ServiceLoader` dựa trên resource này để phát hiện provider trong các thư mục hoặc JAR thuộc classpath của class loader liên quan.

Đây là cơ chế đã có từ Java 6 nhưng **vẫn là API chuẩn, đang hoạt động trên JDK hiện đại**. Nó đặc biệt hữu ích với plugin, adapter, bộ mã hóa, formatter và nhiều trường hợp cần lắp ghép implementation qua thư viện.

**Các vai trò cần phân biệt:**

| Thành phần | Chịu trách nhiệm |
| --- | --- |
| Service type | Interface hoặc abstract class biểu diễn hợp đồng chung, ví dụ `demo.spi.Greeter` |
| Provider class | Lớp công khai triển khai service, ví dụ `demo.impl.EnglishGreeter` |
| Provider-configuration file | Resource `META-INF/services/<tên-service>` chứa tên các provider |
| Consumer | Ứng dụng gọi `ServiceLoader.load(Greeter.class)` rồi dùng các provider qua interface |
| Runtime classpath/class loader | Quyết định resource và lớp provider nào thực sự có thể được tìm thấy |

Việc chỉ tạo lớp `implements Greeter` **chưa tự đăng ký** lớp đó. Tương tự, tạo tệp cấu hình đúng nhưng không đưa tệp ấy vào classpath khi chạy cũng khiến `ServiceLoader` không tìm được provider.

## 2. Quy tắc chính xác của META-INF/services

Với service type `demo.spi.Greeter`, tên và vị trí resource là:

~~~text
META-INF/services/demo.spi.Greeter
~~~

File có nội dung ví dụ:

~~~text
# Mỗi dòng là tên nhị phân đầy đủ của một lớp provider
demo.impl.EnglishGreeter
demo.impl.VietnameseGreeter
~~~

Các quy tắc cần nhớ:

1. **Tên tệp** phải là *fully qualified binary name* của service type, không phải tên lớp triển khai. Với top-level interface thông thường, đó là tên package + tên interface, như `demo.spi.Greeter`. Nếu service type là lớp lồng nhau, binary name dùng ký hiệu `$`.
2. **Nội dung mỗi dòng** là một *fully qualified binary name* của provider class. Không thêm `.class`, không khai báo `new`, `implements`, dấu phẩy hay cú pháp Java khác.
3. Tệp phải được mã hóa bằng **UTF-8**. Nên lưu UTF-8 không BOM, tránh thêm ký tự không mong muốn vào đầu tên provider.
4. Dòng trống và khoảng trắng/tab bao quanh tên provider được bỏ qua. Dấu `#` bắt đầu chú thích đến hết dòng, kể cả sau tên một provider.
5. Tên provider trùng trong một file hoặc giữa các file cấu hình cùng service được bỏ qua khi khám phá provider; không cần tự lặp để tăng mức ưu tiên.
6. Provider class có thể nằm ở JAR khác với file cấu hình, miễn là class loader thích hợp có thể nhìn thấy cả cấu hình và lớp cần nạp.
7. Trên classpath, provider là lớp công khai phù hợp service type, có **constructor công khai, không tham số**; nó sẽ được `ServiceLoader` tạo khi cần. Cơ chế factory method `public static provider()` dành cho provider trong **named module**, không thay thế constructor cho ví dụ classpath này.

**Điểm dễ sai:** file nằm ở `src/main/resources/META-INF/services/...` trong dự án build, nhưng trong output/JAR chạy thực tế nó phải ở **gốc classpath**: `META-INF/services/...`. Nếu bị đóng gói thành `resources/META-INF/services/...`, ServiceLoader mặc định sẽ không đọc được.

## 3. Ví dụ đầy đủ: service và hai provider trên classpath

Ví dụ sau dùng Java 17+ và không yêu cầu thư viện bên ngoài. Cây thư mục:

~~~text
spi-demo/
├── src/
│   └── main/
│       ├── java/
│       │   └── demo/
│       │       ├── spi/
│       │       │   └── Greeter.java
│       │       ├── impl/
│       │       │   ├── EnglishGreeter.java
│       │       │   └── VietnameseGreeter.java
│       │       └── app/
│       │           └── Main.java
│       └── resources/
│           └── META-INF/
│               └── services/
│                   └── demo.spi.Greeter
~~~

### 3.1. Định nghĩa service contract

`src/main/java/demo/spi/Greeter.java`:

~~~java
package demo.spi;

public interface Greeter {
    String id();
    String greet(String name);
}
~~~

`id()` cho ứng dụng biết provider đáp ứng loại nào; `greet()` là hành vi chung. Consumer không cần import bất kỳ implementation nào để dùng hợp đồng này.

### 3.2. Viết provider thứ nhất

`src/main/java/demo/impl/EnglishGreeter.java`:

~~~java
package demo.impl;

import demo.spi.Greeter;

public final class EnglishGreeter implements Greeter {
    public EnglishGreeter() {
    }

    @Override
    public String id() {
        return "en";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Lớp `public`, implements đúng service, constructor không tham số được khai báo `public` rõ ràng.

### 3.3. Viết provider thứ hai

`src/main/java/demo/impl/VietnameseGreeter.java`:

~~~java
package demo.impl;

import demo.spi.Greeter;

public final class VietnameseGreeter implements Greeter {
    public VietnameseGreeter() {
    }

    @Override
    public String id() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chao, " + name + "!";
    }
}
~~~

Ở đây nội dung chuỗi được dùng dạng ASCII để kết quả console giống nhau trên nhiều hệ thống; quy định UTF-8 cho file cấu hình service vẫn giữ nguyên.

### 3.4. Đăng ký provider bằng resource, không sửa consumer

`src/main/resources/META-INF/services/demo.spi.Greeter`:

~~~text
# Greeter implementations on the classpath
demo.impl.EnglishGreeter
demo.impl.VietnameseGreeter
~~~

Tên file là **`demo.spi.Greeter`**, đúng với interface `Greeter`; các dòng bên trong là tên đầy đủ của **hai lớp triển khai**, đúng chữ hoa/chữ thường.

### 3.5. Mã consumer chỉ phụ thuộc vào service type

`src/main/java/demo/app/Main.java`:

~~~java
package demo.app;

import demo.spi.Greeter;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        ServiceLoader<Greeter> greeters =
                ServiceLoader.load(Greeter.class);

        int count = 0;
        for (Greeter greeter : greeters) {
            System.out.println(
                    greeter.id() + " -> " + greeter.greet("An"));
            count++;
        }
        System.out.println("providers=" + count);
    }
}
~~~

Không có `new EnglishGreeter()` hay `new VietnameseGreeter()` trong consumer. Khi vòng lặp chạy, `ServiceLoader` phát hiện và tạo provider từ tên đã đăng ký.

## 4. Biên dịch, đưa resource vào classpath và chạy

Chạy lệnh từ thư mục `spi-demo`. Lệnh `javac` sau dùng đường dẫn tương đối, chạy được với JDK 17+:

~~~bash
javac -encoding UTF-8 -d out src/main/java/demo/spi/Greeter.java src/main/java/demo/impl/EnglishGreeter.java src/main/java/demo/impl/VietnameseGreeter.java src/main/java/demo/app/Main.java
~~~

Lệnh trên tạo các `.class` dưới thư mục `out/demo/...`; **javac không tự sao chép** `src/main/resources`. Cần đặt `META-INF/services` vào thư mục `out`, vì `out` là classpath root của ví dụ.

Trên Linux/macOS (Bash):

~~~bash
cp -R src/main/resources/META-INF out/
java -cp out demo.app.Main
~~~

Trên Windows (PowerShell):

~~~powershell
Copy-Item -Recurse src/main/resources/META-INF out/
java -cp out demo.app.Main
~~~

Output chính xác khi dùng cấu hình của ví dụ:

~~~text
en -> Hello, An!
vi -> Xin chao, An!
providers=2
~~~

Nếu **chưa sao chép** resource `META-INF/services/demo.spi.Greeter` vào `out` và không có provider tương ứng ở nơi khác trên classpath, chạy cùng ứng dụng chỉ cho kết quả:

~~~text
providers=0
~~~

Không có provider nào không tự động là ngoại lệ: iterator đơn giản không trả về phần tử. Ứng dụng cần có chiến lược xử lý nếu dịch vụ là bắt buộc, ví dụ báo lỗi cấu hình hoặc sử dụng một implementation mặc định được chọn rõ ràng.

### 4.1. Đóng gói thành JAR và kiểm tra resource

Sau khi đã copy resource vào `out`, dùng các lệnh sau (có trên JDK 17+):

~~~bash
jar --create --file greeter-demo.jar -C out .
jar --list --file greeter-demo.jar
java -cp greeter-demo.jar demo.app.Main
~~~

Trong kết quả `jar --list` phải có đường dẫn:

~~~text
META-INF/services/demo.spi.Greeter
~~~

`java -cp greeter-demo.jar demo.app.Main` cho cùng output gồm hai provider. Đây là cách kiểm tra quan trọng: **kiểm tra JAR cuối cùng được chạy**, không chỉ đường dẫn source code của dự án.

Trong dự án Maven hoặc Gradle theo convention `src/main/resources`, bước xử lý resources thông thường sẽ đưa resource vào artifact. Tuy vậy, luôn kiểm tra artifact thực tế, đặc biệt khi có quy trình tự đóng gói hoặc gộp nhiều JAR.

## 5. ServiceLoader khám phá và tạo provider như thế nào?

Luồng xử lý khái quát với classpath:

1. Consumer gọi `ServiceLoader.load(Greeter.class)`. Mặc định hàm này dùng **thread context class loader** của luồng hiện tại.
2. Khi duyệt (`iterator`/for-each), loader tìm các resource `META-INF/services/demo.spi.Greeter` mà class loader nhìn thấy.
3. Loader đọc từng tên provider hợp lệ, nạp lớp, xác minh tính tương thích với service type, rồi tạo instance bằng constructor công khai không tham số.
4. Provider được trả về qua biến kiểu `Greeter` và được thêm vào **cache của chính đối tượng ServiceLoader**.

`ServiceLoader` **lazy**: gọi `load` chỉ tạo loader; quá trình tìm và khởi tạo provider được thực hiện theo nhu cầu khi duyệt hoặc gọi các API kích hoạt truy vấn provider. Không nên giả định mọi provider đều được khởi tạo ngay tại lệnh `load`.

### 5.1. Thứ tự và việc chọn provider

Với một file cấu hình đơn lẻ trong ví dụ, provider được liệt kê theo thứ tự hai dòng: English, rồi Vietnamese. Nếu nhiều JAR cùng đăng ký service, thứ tự các file cấu hình phụ thuộc vào cách class loader tìm resource; **không dùng thứ tự phát hiện giữa các JAR làm quy tắc nghiệp vụ**.

Khi có nhiều provider, nên chọn bằng khả năng được khai báo trong interface (như `id()`) thay vì mặc định “provider đầu tiên là tốt nhất”. Ví dụ, đặt đoạn sau vào một phương thức trong ứng dụng:

~~~java
Greeter selected = null;
for (Greeter candidate : ServiceLoader.load(Greeter.class)) {
    if ("vi".equals(candidate.id())) {
        selected = candidate;
        break;
    }
}
if (selected == null) {
    throw new IllegalStateException("Missing vi Greeter provider");
}
System.out.println(selected.greet("An"));
~~~

Đoạn trên minh họa cách chọn, **không phải một tệp Java độc lập**. Nếu chạy trong chương trình có provider `VietnameseGreeter`, nó in `Xin chao, An!`.

### 5.2. Cache và reload

Một đối tượng `ServiceLoader` lưu cache các provider đã được tạo khi duyệt. Duyệt lại cùng loader sẽ có thể dùng lại những instance đã cache; tạo một `ServiceLoader` mới tạo cache riêng.

`reload()` xóa cache để các lần duyệt tiếp theo tìm/tạo lại provider. Nhưng `reload()` **không tự thêm file JAR mới vào classpath** hoặc sửa khả năng nhìn thấy resource của class loader. Nếu hệ thống có plugin thay đổi khi chạy, việc quản lý class loader và lifecycle là trách nhiệm riêng.

`ServiceLoader` không an toàn để nhiều luồng sử dụng đồng thời trên cùng một instance. Khi cần xử lý đồng thời, phải tổ chức vùng sở hữu và đồng bộ thích hợp.

### 5.3. Khi cần chỉ định class loader

Có thể gọi:

~~~java
ServiceLoader<Greeter> loader =
        ServiceLoader.load(Greeter.class, myClassLoader);
~~~

Đây là đoạn minh họa, với `myClassLoader` là một `ClassLoader` đã được khởi tạo ở nơi khác. Nó hữu ích cho môi trường plugin có class loader riêng. Nếu tạo loader bằng overload một tham số, `ServiceLoader.load(Greeter.class)` dùng context class loader hiện tại; provider có tồn tại trên disk nhưng không được class loader đó thấy thì vẫn không được tìm ra.

## 6. Những lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/sửa |
| --- | --- | --- |
| `providers=0` | Thiếu config file hoặc file không nằm tại classpath root | Dùng `jar --list --file ...`, kiểm tra đúng `META-INF/services/demo.spi.Greeter` |
| `providers=0` | Sai tên service trong tên file (viết tên provider thay vì tên interface, sai package/hoa-thường) | So khớp chính xác `Greeter.class.getName()` với tên file |
| `providers=0` | Chạy với classpath khác với lúc build, hoặc resource bị thiếu khi đóng gói | Xem tham số `-cp` và nội dung artifact được chạy |
| `ServiceConfigurationError` lúc duyệt | Tên provider sai, lớp không tồn tại/không được class loader thấy | Soát mỗi dòng tên đầy đủ và dependency runtime |
| `ServiceConfigurationError` lúc duyệt | Provider không implement service, không có public no-arg constructor hoặc constructor thất bại | Sửa khai báo lớp và constructor; xem cause của lỗi |
| Một số provider biến mất sau khi gộp JAR | Các file cùng tên `META-INF/services/<service>` bị ghi đè thay vì gộp | Cấu hình công cụ đóng gói để bảo toàn/gộp nội dung service descriptor |
| Khác số lượng provider giữa các môi trường | Runtime classpath, resource hoặc class loader khác nhau | Kiểm tra artifact, dependencies và context class loader tương ứng |

**Phân biệt hai trường hợp:** “không tìm thấy provider” dẫn đến kết quả duyệt rỗng; “tìm thấy cấu hình nhưng cấu hình/provider không hợp lệ” thường dẫn đến `ServiceConfigurationError` khi khám phá hoặc khởi tạo. Đừng bắt lỗi cấu hình rồi lặng lẽ giả vờ như không có provider trong trường hợp dịch vụ đó là yêu cầu bắt buộc.

Để xem class loader tìm được bao nhiêu descriptor cho service, có thể chạy đoạn kiểm tra sau trong một phương thức khi cần debug (đã import `java.util.*`):

~~~java
ClassLoader cl = Thread.currentThread().getContextClassLoader();
String resourceName = "META-INF/services/" + Greeter.class.getName();
Enumeration<java.net.URL> locations = cl.getResources(resourceName);
while (locations.hasMoreElements()) {
    System.out.println(locations.nextElement());
}
~~~

Đây chỉ là **đoạn chẩn đoán** (có thể ném `IOException`), không phải chương trình độc lập. Nó giúp nhận diện config file trong classpath, nhưng còn phải kiểm tra lớp provider tương ứng có tải được hay không.

## 7. Ranh giới với hệ module Java hiện đại (JPMS)

Bài này tập trung **đăng ký provider bằng META-INF/services khi chạy trên classpath**. Java 9 trở lên còn có cách cung cấp service bằng **named modules**, và hai cách không nên bị nhầm:

| Môi trường triển khai | Cách khai báo provider |
| --- | --- |
| Lớp/JAR không phải named module, chạy trên `-cp` | Tệp `META-INF/services/<tên-service>` |
| Named module rõ ràng trên module path | Chỉ thị `provides ... with ...` trong `module-info.java`; consumer module khai báo `uses ...` |
| JAR không có `module-info.class` nhưng được dùng như automatic module trên module path | Có thể suy ra provider từ `META-INF/services` theo cơ chế automatic module |

Ví dụ minh họa cú pháp module descriptor cho **module provider** (không sử dụng nó trong demo classpath ở trên):

~~~java
module demo.provider {
    requires demo.api;
    provides demo.spi.Greeter
        with demo.impl.EnglishGreeter, demo.impl.VietnameseGreeter;
}
~~~

Nếu ứng dụng consumer là một named module, nó cần khai báo `uses demo.spi.Greeter;` trong module descriptor của mình. Provider trong named module được khai báo bằng `provides`; không nên trông chờ chỉ riêng descriptor `META-INF/services` thay thế quy tắc khai báo của named module. Ngược lại, một modular JAR khi chạy **trên classpath** vẫn được đối xử như classpath JAR.

**Lựa chọn thực tiễn:** nếu ứng dụng và plugin đang triển khai bằng classpath, `META-INF/services` vẫn là cơ chế chuẩn và hợp lệ; nếu toàn bộ hệ thống sử dụng named modules, hãy dùng ngữ nghĩa `uses`/`provides` tương ứng.

## 8. Những nguyên tắc áp dụng vào dự án

- Thiết kế interface service **nhỏ, ổn định và đủ thông tin chọn provider**; tách hành vi dùng chung khỏi implementation.
- Đưa `META-INF/services` vào **resources**, để công cụ build đóng gói giống tài nguyên thường; xác nhận vị trí trong JAR sau cùng.
- Provider nên có constructor công khai không tham số và không làm các việc nặng/không cần thiết ngay lúc khởi tạo. Tránh phụ thuộc vào thứ tự giữa các file cấu hình khác nhau.
- Nếu nhiều library đóng góp provider cho cùng một service, cấu hình bước tạo “fat/shaded JAR” để **gộp** descriptor; đừng để provider cuối cùng ghi đè mất các tên trước.
- Khi triển khai plugin nạp động, phải xem xét **class loader, lifecycle, cache và concurrency**; file cấu hình chỉ giải quyết việc đăng ký, không tự quản lý hot reload.
- Xử lý rõ tình huống không có provider phù hợp và phân biệt nó với **provider hỏng**. Việc chọn provider nên dựa trên chức năng được công bố qua contract.

## 9. Tự kiểm tra

**Câu 1:** Nếu interface là `com.app.spi.ExportService` và implementation là `com.app.csv.CsvExporter`, tên file đăng ký trên classpath là gì?

**Đáp án:** `META-INF/services/com.app.spi.ExportService`; file chứa một dòng `com.app.csv.CsvExporter`.

**Câu 2:** Nếu `CsvExporter.class` đã có trong JAR nhưng không có file đăng ký, `ServiceLoader.load(ExportService.class)` có tự tìm ra lớp theo tên “CsvExporter” không?

**Đáp án:** Không. Trong triển khai classpath, phải có descriptor hợp lệ và class loader nhìn thấy nó (hoặc một cơ chế đăng ký service tương ứng khác).

**Câu 3:** Trong ví dụ demo, nếu xóa dòng `demo.impl.VietnameseGreeter` khỏi resource rồi build lại từ đầu, output nào còn?

**Đáp án:**

~~~text
en -> Hello, An!
providers=1
~~~

**Câu 4:** Vì sao `jar --list` có file resource nhưng vẫn có thể bị `ServiceConfigurationError` khi duyệt?

**Đáp án:** Resource chỉ là danh sách tên; nó không chứng minh các class thực thi được tải, có type tương thích và constructor công khai không tham số. Cần xác minh cả dependency/runtime class loader và lớp provider.

**Câu 5:** Có nên dùng “implementation đầu tiên được tìm thấy” làm quy tắc chọn plugin quan trọng trong hệ thống nhiều JAR không?

**Đáp án:** Không. Thứ tự resource giữa các JAR phụ thuộc class loader; hãy chọn bằng metadata/capability của service hoặc cấu hình ưu tiên rõ ràng.

## 10. Tài liệu chính thức để đối chiếu

- [Java SE 26 — ServiceLoader: Deploying service providers on the class path](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
- [Java SE 26 — JAR File Specification: META-INF/services](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
- [Java SE 27 — Java Platform specification index](https://docs.oracle.com/en/java/javase/27/docs/specs/index.html)

Ví dụ chạy và đóng gói sử dụng công cụ JDK 17+ hiện hành. Cơ chế classpath `META-INF/services` vẫn áp dụng trên Java hiện đại, không phụ thuộc vào tiện ích hoặc đường dẫn triển khai Java cổ đã ngừng sử dụng.
