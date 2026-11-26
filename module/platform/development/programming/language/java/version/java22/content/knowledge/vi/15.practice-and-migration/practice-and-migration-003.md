# Quy tắc biên dịch và chạy preview trong cùng phiên bản JDK; phân biệt với incubator

## 1. Phạm vi và mục tiêu

Khi nâng cấp một dự án từng thử nghiệm tính năng trong Java 22, cần xác định lại trạng thái của từng tính năng ở JDK đích. Một tính năng từng là preview có thể đã trở thành chính thức; một API incubator vẫn có thể cần được đưa vào đồ thị module.

Bài học trình bày các quy tắc còn áp dụng trong Java hiện đại: chọn đúng compiler và runtime, bật preview ở đúng giai đoạn, nhận diện class file phụ thuộc preview và sử dụng module incubator. Các ví dụ thực thi hiện hành dùng JDK 27; những lệnh có số phiên bản 22 chỉ minh họa quy tắc phiên bản khi xử lý một bản dựng Java 22.

Trong bài, **N là phiên bản tính năng của Java**, chẳng hạn 22 hoặc 27. Đây là số trong `--release N`, không phải số bản vá hay số thứ tự lần preview của một JEP.

## 2. Preview và incubator giải quyết hai việc khác nhau

Preview cho phép dùng thử một tính năng đã có thiết kế và triển khai đầy đủ nhưng chưa được chốt lâu dài. Preview có thể là tính năng ngôn ngữ, tính năng JVM hoặc API. Incubator đưa API đang được phát triển đến người dùng qua các module riêng của JDK, chẳng hạn `jdk.incubator.vector`.

Vì vậy, không thể nhận biết trạng thái một tính năng chỉ bằng việc nó là cú pháp hay API. `StructuredTaskScope` là một API preview trong `java.util.concurrent`, còn Vector API nằm trong module incubator.

| Tiêu chí | Preview | Incubator, minh họa bằng Vector API |
| --- | --- | --- |
| Cách nhận biết | Tài liệu/JEP và nhãn preview của phiên bản đang dùng | Module và package `jdk.incubator.vector`, nhãn incubating |
| Cho phép compiler dùng tính năng | `--enable-preview` cùng mức nguồn phù hợp | Làm module khả dụng, thường bằng `--add-modules` |
| Cho phép runtime sử dụng | `--enable-preview` cho class phụ thuộc preview | Đưa module vào đồ thị module khi khởi chạy |
| Ràng buộc đặc thù | Class phụ thuộc preview bị ràng buộc với đúng phiên bản Java | API/module có thể thay đổi; không có bảo đảm tương thích dài hạn |
| Có tự cần cơ chế còn lại không? | Không tự cần `--add-modules` | Không tự cần `--enable-preview` chỉ vì là incubator |

Đặc tả phân biệt các loại preview trong [JLS §1.5](https://docs.oracle.com/javase/specs/jls/se27/html/jls-1.html#jls-1.5). Trạng thái incubator hiện hành của Vector API được ghi tại [module jdk.incubator.vector của JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/module-summary.html).

## 3. Kiểm tra trạng thái hiện tại trước khi giữ lại cờ cũ

Không nên bật preview cho toàn bộ dự án chỉ vì dự án từng dùng nó ở Java 22.

| Tính năng liên quan đến Java 22 | Trạng thái dùng trong Java 27 | Hệ quả khi cấu hình |
| --- | --- | --- |
| Unnamed Variables and Patterns | Chính thức từ Java 22 | Không cần preview chỉ để dùng tính năng này |
| Foreign Function & Memory API | API chính thức từ Java 22 | Không cần preview chỉ vì dùng FFM; quyền native access là vấn đề riêng |
| Stream Gatherers | API chính thức từ Java 24 | Không cần preview cho Gatherers ở JDK 27 |
| Scoped Values | API chính thức từ Java 25 | Không cần preview cho Scoped Values ở JDK 27 |
| Structured Concurrency | Vẫn là preview ở JDK 27 | Cần cấu hình preview nếu dùng API này |
| Vector API | Vẫn là incubator ở JDK 27 | Cần làm module `jdk.incubator.vector` khả dụng |

Nguồn kiểm tra: [lịch sử thay đổi ngôn ngữ](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html), [java.lang.foreign](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/package-summary.html), [Gatherer](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Gatherer.html), [ScopedValue](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html) và [StructuredTaskScope](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

Bảng này cho biết tính năng có cần preview ở JDK đích hay không. Nó không khẳng định mã nguồn dùng API preview cũ sẽ biên dịch nguyên vẹn bằng API hiện tại. Khi nâng cấp, vẫn cần đối chiếu chữ ký API và hành vi.

## 4. Quy tắc cốt lõi: preview của N phải dùng compiler và runtime N

Đối với mã dùng preview của Java N:

1. Dùng `javac` thuộc JDK N.
2. Biên dịch với `--enable-preview --release N`, hoặc `--enable-preview --source N`.
3. Dùng `java` thuộc phiên bản N và bật `--enable-preview` để chạy các class phụ thuộc preview.

Dạng lệnh khái quát, trong đó phải thay N bằng một số phiên bản cụ thể:

```text
javac --enable-preview --release N -d out App.java
java --enable-preview -cp out App
```

Quy tắc này được mô tả trong [hướng dẫn Preview Features của Oracle](https://docs.oracle.com/en/java/javase/27/language/preview-language-vm-features.html).

### 4.1. “Cùng phiên bản” có nghĩa gì?

Compiler và runtime phải cùng phiên bản tính năng Java mà preview thuộc về. Ví dụ, preview Java 22 gắn với Java 22; preview Java 27 gắn với Java 27.

Quy tắc này không yêu cầu hai công cụ có cùng một số bản vá cụ thể. Tuy vậy, để tái lập bản dựng và điều tra lỗi thuận tiện, dự án có thể chủ động cố định cả nhà cung cấp và bản cập nhật JDK trong toolchain.

Số lần preview của JEP cũng không thay thế số phiên bản Java. Ví dụ, một tính năng được giới thiệu là “Seventh Preview” trong JDK 27 vẫn dùng `--release 27`, không dùng `--release 7`.

### 4.2. JDK mới hơn không cung cấp chế độ chạy preview của mọi JDK cũ

| Artifact hoặc thao tác | Môi trường | Kết quả theo quy tắc phiên bản |
| --- | --- | --- |
| Class phụ thuộc preview Java 22 | Java 22, bật preview | Đáp ứng điều kiện phiên bản và preview |
| Class phụ thuộc preview Java 22 | Java 22, không bật preview | Bị từ chối khi nạp class đó |
| Class phụ thuộc preview Java 22 | Java 27, bật preview | Vẫn bị từ chối vì khác phiên bản |
| Biên dịch preview Java 22 | `javac` 27 với `--release 22 --enable-preview` | Không được hỗ trợ |
| Class phụ thuộc preview Java 27 | Java 27, bật preview | Đáp ứng điều kiện phiên bản và preview |

“Đáp ứng điều kiện” ở đây không loại trừ lỗi độc lập như thiếu thư viện, sai module path hoặc lỗi nghiệp vụ.

Khi chuyển từ một bản preview cũ sang JDK mới, cần biên dịch lại mã nguồn cho JDK đích. Đổi runtime và thêm cờ không chuyển đổi artifact preview cũ thành artifact mới.

## 5. Ví dụ preview hiện hành: Structured Concurrency trên JDK 27

Đoạn mã dùng API preview hiện hành của JDK 27. Nó minh họa cách cấu hình compiler/runtime, không phải chữ ký API của bản preview Java 22.

Tệp `PreviewDemo.java`:

```java
import java.util.concurrent.StructuredTaskScope;

public class PreviewDemo {
    public static void main(String[] args) throws Exception {
        try (var scope = StructuredTaskScope.open()) {
            var itemCost = scope.fork(() -> 120);
            var deliveryCost = scope.fork(() -> 15);

            scope.join();

            int total = itemCost.get() + deliveryCost.get();
            System.out.println(total);
        }
    }
}
```

Với `javac` và `java` đều thuộc JDK 27:

```shell
javac --enable-preview --release 27 -Xlint:preview -encoding UTF-8 -d out-preview PreviewDemo.java
java --enable-preview -cp out-preview PreviewDemo
```

Kết quả nghiệp vụ dự kiến:

```text
135
```

`-Xlint:preview` yêu cầu compiler hiển thị thông tin sử dụng preview. Đây là tùy chọn chẩn đoán; cờ cho phép sử dụng tính năng là `--enable-preview`.

Ví dụ cố ý dùng chữ ký `public static void main(String[] args)` quen thuộc để phần cần bật preview được tập trung vào API `StructuredTaskScope`.

Những thay đổi để quan sát cơ chế:

- Bỏ `--enable-preview` khỏi lệnh biên dịch: compiler từ chối các tham chiếu API preview thông thường.
- Biên dịch thành công nhưng bỏ cờ khỏi lệnh chạy: runtime từ chối nạp class phụ thuộc preview.
- Giữ cờ nhưng chạy artifact bằng Java khác phiên bản: cờ không khắc phục được sai phiên bản.

Quy tắc cho API preview thông thường và ngoại lệ dành cho một số API preview phản chiếu được quy định trong [JLS §1.5.1](https://docs.oracle.com/javase/specs/jls/se27/html/jls-1.html#jls-1.5.1). Không nên suy rộng rằng mọi API có nhãn preview đều có cách xử lý cảnh báo hoàn toàn giống nhau; hãy kiểm tra tài liệu của API đang dùng.

## 6. Vì sao class preview không chạy trên JDK mới hơn?

Class file lưu phiên bản định dạng qua hai trường `major_version` và `minor_version`. Với các phiên bản Java đang xét, minor `65535` biểu thị class phụ thuộc preview.

Ví dụ Java 22:

| Loại class file | Major | Minor |
| --- | --- | --- |
| Class thông thường nhắm Java 22 | 66 | 0 |
| Class phụ thuộc preview Java 22 | 66 | 65535 |

JVM Java 22 chỉ cho phép nạp dạng `66.65535` khi preview được bật. Chi tiết định dạng được quy định tại [JVMS Java 22 §4.1](https://docs.oracle.com/javase/specs/jvms/se22/html/jvms-4.html#jvms-4.1).

Với Java 27, major là 71. JVM Java 27 có thể chấp nhận `71.65535` khi bật preview, nhưng không được nạp class có dấu preview thuộc phiên bản trước, chẳng hạn `66.65535`. Xem [JVMS Java 27 §4.1](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html#jvms-4.1).

Có thể quan sát class của ví dụ bằng công cụ cùng JDK:

```shell
javap -verbose -classpath out-preview PreviewDemo
```

Trong kết quả, tìm các trường phiên bản. Với class ví dụ được biên dịch bằng JDK 27 và có phụ thuộc preview, các giá trị cần quan sát là:

```text
minor version: 65535
major version: 71
```

Không phải mọi class được biên dịch trong một lần chạy `javac --enable-preview` đều nhất thiết mang dấu preview. Cờ cho phép compiler xử lý preview; dấu trong artifact phụ thuộc vào class được sinh ra và các quy tắc đánh dấu.

Việc tính năng về sau trở thành chính thức cũng không sửa lại bytecode cũ. Artifact cũ vẫn giữ dấu preview của lần biên dịch trước và phải được biên dịch lại nếu chuyển sang runtime mới.

## 7. Phân biệt --release, --source và --target

Ba tùy chọn này không có cùng mục đích:

| Tùy chọn | Vai trò chính |
| --- | --- |
| `--source N` | Chọn quy tắc ngôn ngữ ở mức nguồn N |
| `--target N` | Chọn phiên bản định dạng class file đầu ra |
| `--release N` | Chọn mức ngôn ngữ, mục tiêu class file và tập API nền tảng tương ứng N |

Với mã Java thông thường cần nhắm một phiên bản trước mà compiler hỗ trợ, `--release` giúp tránh việc vô tình gọi API nền tảng mới hơn runtime đích.

Ví dụ sau chỉ dành cho mã **không dùng preview**:

```shell
javac --release 22 -d out-java22 App.java
```

Một compiler hiện đại có hỗ trợ release 22 có thể biên dịch mã thông thường theo mức đó. Điều này không có nghĩa nó có thể biên dịch preview của Java 22.

Lệnh sau không hợp lệ khi `javac` đang thuộc JDK 27:

```shell
javac --enable-preview --release 22 App.java
```

Không thể dùng `--source 22` hay `--target 22` để vượt qua giới hạn preview theo phiên bản. Cũng không được kết hợp `--release` với `--source` hoặc `--target` trong cùng lệnh.

Các vai trò và giới hạn kết hợp tùy chọn được ghi trong [tài liệu javac JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html#standard-options). Với bản dựng Java 22 cần tái lập, hãy dùng [javac của chính JDK 22](https://docs.oracle.com/en/java/javase/22/docs/specs/man/javac.html).

Lưu ý rằng `--release` kiểm soát API nền tảng; nó không tự bảo đảm mọi dependency bên thứ ba đều phù hợp với runtime đích.

## 8. Incubator qua ví dụ Vector API

### 8.1. Ứng dụng chạy trên class path

Tệp `VectorDemo.java`:

```java
import jdk.incubator.vector.IntVector;

public class VectorDemo {
    public static void main(String[] args) {
        var species = IntVector.SPECIES_PREFERRED;

        var left = IntVector.broadcast(species, 3);
        var right = IntVector.broadcast(species, 4);

        var result = left.add(right);
        System.out.println(result.lane(0));
    }
}
```

Với JDK 27 có module `jdk.incubator.vector`:

```shell
javac --add-modules jdk.incubator.vector -d out-vector VectorDemo.java
java --add-modules jdk.incubator.vector -cp out-vector VectorDemo
```

Giá trị nghiệp vụ dự kiến là `7`. JDK có thể đồng thời in thông báo về việc dùng module incubator.

Ở đây, `--add-modules` làm module trở thành một phần của đồ thị module được giải quyết. Ví dụ không dùng preview ngôn ngữ hay API preview riêng nào, nên không cần thêm `--enable-preview`.

Các thao tác vector được dùng ở trên có trong [API IntVector JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.incubator.vector/jdk/incubator/vector/IntVector.html). Mục tiêu của ví dụ là cấu hình module; nó không phải phép đo hiệu năng SIMD.

### 8.2. Có trong JDK chưa đồng nghĩa đã được đưa vào đồ thị module

Có thể kiểm tra runtime có chứa module bằng:

```shell
java --list-modules
```

Sau đó tìm `jdk.incubator.vector` trong danh sách.

Hai tình huống cần phân biệt:

- Module có mặt trong runtime nhưng chưa được giải quyết cho ứng dụng: cần cấu hình đồ thị module.
- Module không có trong runtime, chẳng hạn runtime tùy biến đã lược bỏ nó: chỉ thêm `--add-modules` không thể tạo ra module đang thiếu.

Một câu lệnh `import` chỉ giúp mã nguồn tham chiếu tên kiểu. Nó không thay thế cấu hình module.

### 8.3. Ứng dụng JPMS có module-info.java

Nếu ứng dụng là named module, có thể khai báo phụ thuộc trực tiếp:

```java
module demo.vector {
    requires jdk.incubator.vector;
}
```

Cấu trúc nguồn minh họa:

```text
src/
  demo.vector/
    module-info.java
    demo/
      vector/
        VectorDemo.java
```

Trong trường hợp này, thêm khai báo sau vào đầu `VectorDemo.java` của ví dụ:

```java
package demo.vector;
```

Biên dịch và chạy:

```shell
javac --module-source-path src -d out-module -m demo.vector
java --module-path out-module -m demo.vector/demo.vector.VectorDemo
```

Vì module gốc `demo.vector` khai báo `requires jdk.incubator.vector`, phụ thuộc được giải quyết thông qua khai báo đó; không cần lặp lại `--add-modules jdk.incubator.vector` trong đúng cấu hình minh họa này.

Cơ chế module path, root module và `--add-modules` được mô tả trong [tài liệu lệnh java](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html) và [phần cấu hình module của javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html#configuring-the-module-system).

## 9. Khi ứng dụng đồng thời dùng preview và incubator

Một ứng dụng có thể dùng Structured Concurrency để điều phối tác vụ, còn từng tác vụ sử dụng Vector API. Khi đó phải thỏa cả điều kiện preview và điều kiện module.

Tệp `MixedDemo.java`, dùng API của JDK 27:

```java
import java.util.concurrent.StructuredTaskScope;
import jdk.incubator.vector.IntVector;

public class MixedDemo {
    public static void main(String[] args) throws Exception {
        var species = IntVector.SPECIES_PREFERRED;

        try (var scope = StructuredTaskScope.open()) {
            var left = scope.fork(
                    () -> IntVector.broadcast(species, 3));
            var right = scope.fork(
                    () -> IntVector.broadcast(species, 4));

            scope.join();

            var total = left.get().add(right.get());
            System.out.println(total.lane(0));
        }
    }
}
```

Với compiler và runtime đều thuộc JDK 27:

```shell
javac --enable-preview --source 27 --add-modules jdk.incubator.vector -d out-mixed MixedDemo.java
java --enable-preview --add-modules jdk.incubator.vector -cp out-mixed MixedDemo
```

Lệnh biên dịch này dùng `--source 27` để chọn mức nguồn preview hiện tại, cùng API từ JDK 27 đang dùng. Kết quả nghiệp vụ dự kiến là `7`.

| Nếu thiếu | Vấn đề còn lại |
| --- | --- |
| Cờ preview khi biên dịch | Tham chiếu API preview bị từ chối |
| Cờ preview khi chạy | Class có phụ thuộc preview không được nạp |
| Module Vector khi biên dịch | Kiểu `IntVector` không khả dụng cho việc biên dịch |
| Module Vector khi chạy | Module/API cần thiết không khả dụng cho ứng dụng |
| Đúng phiên bản runtime | Preview vẫn bị từ chối dù các cờ còn lại có mặt |

Không nên bật cả hai cơ chế cho mọi ứng dụng. Hãy lấy danh sách tính năng và module thực sự dùng làm cơ sở cấu hình.

## 10. Kiểm soát compiler, test JVM và runtime triển khai

Trong dự án thực tế, “đã bật preview” cần được kiểm tra theo từng tiến trình.

| Giai đoạn | Điều cần đồng bộ |
| --- | --- |
| Biên dịch mã chính | Compiler N, mức nguồn N và cờ preview nếu cần |
| Biên dịch mã kiểm thử | Compiler/mức nguồn phù hợp; bật preview nếu mã kiểm thử tham chiếu tính năng hoặc class phụ thuộc preview |
| Chạy kiểm thử | JVM N; bật preview nếu kiểm thử nạp class phụ thuộc preview |
| Chạy từ IDE | JDK dự án, cấu hình ngôn ngữ và VM options của cấu hình chạy |
| Chạy ứng dụng đóng gói | Runtime N và các tùy chọn JVM/module cần thiết |
| Chạy trong container | JDK ở bước build, Java ở bước chạy và module có mặt trong image |

Một công cụ build có thể chạy trên một JVM nhưng dùng toolchain khác để biên dịch, rồi khởi tạo thêm JVM riêng để chạy kiểm thử. Cờ đặt cho một tiến trình không tự chuyển sang mọi tiến trình còn lại.

Khi điều tra lỗi, bắt đầu bằng:

```shell
javac --version
java --version
```

Hai dòng này chỉ kiểm tra công cụ được shell hiện tại tìm thấy. Với IDE, CI hoặc toolchain của công cụ build, cần xem đúng executable và phiên bản mà từng bước thực sự sử dụng.

### 10.1. Kiểm tra đường dẫn trên PowerShell

Trên Windows, có thể xem các lệnh được tìm thấy bằng:

```powershell
Get-Command javac -All | Select-Object Source
Get-Command java -All | Select-Object Source
```

Nếu cần thử với một JDK cụ thể, gọi trực tiếp executable của bản cài đó. Ví dụ sau giả định JDK 27 đã được cài tại đường dẫn minh họa:

```powershell
$previewJdkPath = 'C:\Java\jdk-27'

& "$previewJdkPath\bin\javac.exe" --version
& "$previewJdkPath\bin\java.exe" --version

& "$previewJdkPath\bin\javac.exe" --enable-preview --release 27 -d out-preview PreviewDemo.java
& "$previewJdkPath\bin\java.exe" --enable-preview -cp out-preview PreviewDemo
```

Biến trên chỉ chọn đường dẫn cho các lệnh minh họa. Phải thay nó bằng vị trí cài JDK thực tế.

### 10.2. Vị trí cờ khi khởi chạy

Các tùy chọn JVM phải đứng trước tên lớp hoặc `-jar`:

```shell
java --enable-preview -cp out-preview PreviewDemo
java --enable-preview -jar app.jar
```

Lệnh thứ hai giả định JAR đã có main class phù hợp và chứa các class cần chạy.

Với lệnh sau, chuỗi `--enable-preview` nằm ở vị trí đối số ứng dụng:

```shell
java -cp out-preview PreviewDemo --enable-preview
```

Nó không bật preview cho JVM. Việc đưa class vào JAR cũng không thay đổi dấu preview hoặc các yêu cầu phiên bản của class đó.

## 11. Chẩn đoán lỗi theo đúng nguyên nhân

Thông báo cụ thể có thể khác giữa các phiên bản công cụ, nhưng nên phân loại như sau:

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Compiler báo preview bị tắt | Thiếu `--enable-preview` | Bật ở lệnh compiler thực sự dùng |
| Compiler báo preview chỉ được hỗ trợ cho release hiện tại | Đang bật preview với mức nguồn khác phiên bản compiler | Dùng compiler đúng N hoặc chuyển mã sang preview/API của JDK đích |
| Runtime báo preview chưa được bật | JVM nạp class có dấu preview nhưng thiếu cờ | Thêm cờ cho đúng tiến trình Java |
| Runtime báo class preview thuộc phiên bản khác | Artifact preview được tạo bằng Java khác phiên bản | Biên dịch lại cho JDK đích |
| `UnsupportedClassVersionError` với major mới hơn runtime | Compiler/target cao hơn Java đang chạy | Đồng bộ runtime và mục tiêu biên dịch |
| Package Vector không ở trong đồ thị module | Module có mặt nhưng chưa được giải quyết | Dùng `--add-modules` hoặc `requires` phù hợp |
| `Module ... not found` | Runtime hoặc module path thiếu module cần thiết | Kiểm tra bản JDK/runtime image và module path |
| Build vẫn dùng class preview cũ sau nâng cấp | Output hoặc dependency cũ còn được tái sử dụng | Tạo lại artifact từ nguồn và cập nhật dependency tương ứng |
| Build dừng khi có cảnh báo | Chính sách như `-Werror` đang áp dụng | Xác định loại cảnh báo và cấu hình chính sách có chủ đích |

`-Xlint:preview` giúp nhìn rõ vị trí dùng preview. Tắt cảnh báo không thay thế việc bật tính năng, không thay đổi phiên bản class file và không tạo cam kết tương thích cho API.

Không dùng các cờ mở truy cập như `--add-exports` hoặc `--add-opens` để chữa lỗi chưa bật preview. Chúng điều chỉnh khả năng truy cập module, không thay đổi quy tắc preview theo phiên bản.

Khi tái lập lỗi, nên dùng thư mục đầu ra mới như các thư mục `out-preview`, `out-vector` và `out-mixed` trong bài. Cách này giúp tránh nhầm class của lần thử trước với artifact vừa biên dịch.

## 12. Nâng cấp một dự án đã dùng preview trong Java 22

Quy trình thực hành đề xuất:

1. **Liệt kê nơi dùng tính năng:** tách cú pháp ngôn ngữ, API preview, module incubator và thư viện bên thứ ba.
2. **Chọn JDK đích:** kiểm tra trạng thái và API của từng tính năng trong đúng tài liệu phiên bản đó.
3. **Chuyển mã nguồn:** sửa chữ ký API hoặc cách gọi theo JDK đích, nếu có thay đổi.
4. **Biên dịch lại:** tạo artifact mới bằng toolchain đã chọn; không tái sử dụng class preview của Java 22.
5. **Đồng bộ nơi chạy:** kiểm thử, IDE, CI và môi trường triển khai cần có runtime cùng phiên bản với preview còn được dùng.
6. **Thu gọn cờ:** giữ preview và module incubator đúng theo phụ thuộc thực tế.
7. **Kiểm tra artifact cuối:** xác nhận class version, dependency và cách khởi chạy ứng dụng đã đóng gói.

Ví dụ một dự án Java 22 trước đây dùng Scoped Values và Vector API, nay chuyển sang JDK 27:

- Chuyển phần Scoped Values sang API hiện hành rồi biên dịch lại. Bản thân Scoped Values đã chính thức, nên không cần preview chỉ cho phần này.
- Phần dùng Vector API vẫn phải có module `jdk.incubator.vector`.
- Nếu dự án bổ sung hoặc vẫn sử dụng Structured Concurrency hiện hành, cần giữ cờ preview cho phần biên dịch và các JVM nạp class phụ thuộc preview.
- Nếu không còn bất kỳ phụ thuộc preview nào khác, có thể bỏ cờ preview sau khi xác minh lại toàn bộ bản dựng.

Điều cần lưu cùng cấu hình dự án là: phiên bản JDK đích, các tính năng còn preview, các module incubator cần thiết và tùy chọn cho từng tiến trình. Những thông tin đó giúp lần nâng cấp tiếp theo bắt đầu từ trạng thái thực tế của dự án.