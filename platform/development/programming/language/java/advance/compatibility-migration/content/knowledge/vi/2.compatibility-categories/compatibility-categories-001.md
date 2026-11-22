# Tương thích mã nguồn: biên dịch lại mã cũ với phiên bản mới

Khi nâng cấp Java, thư viện hoặc nền tảng build, một câu hỏi quan trọng là: **mã nguồn đã viết cho phiên bản cũ có còn biên dịch được khi dùng phiên bản mới hay không?** Khả năng đó được gọi là *tương thích mã nguồn* (*source compatibility*).

Tương thích mã nguồn đặc biệt quan trọng trong các dự án có nhiều module, nhiều nhóm phát triển hoặc một thư viện được nhiều ứng dụng sử dụng. Một thay đổi API có thể khiến hàng chục dự án phải sửa mã cùng lúc. Ngược lại, nếu nhà phát triển thư viện duy trì được tương thích mã nguồn, người dùng có thể nâng cấp dependency và biên dịch lại mà ít phải thay đổi code.

## 1. Tương thích mã nguồn là gì?

Một phiên bản mới có tương thích mã nguồn với phiên bản cũ khi mã nguồn hợp lệ trước đây vẫn có thể được biên dịch trong môi trường mới, với các điều kiện biên dịch tương đương và những dependency cần thiết.

Ví dụ, ứng dụng đang dùng phiên bản 1 của thư viện `text-kit`:

```java
String displayName = TextKit.normalize(input);
```

Khi nâng lên phiên bản 2, nếu phương thức `normalize(String)` vẫn tồn tại và giữ cách sử dụng tương thích, ứng dụng có thể biên dịch lại mà không cần sửa dòng code trên. Nếu phương thức bị xóa, đổi tên hoặc thay đổi kiểu dữ liệu khiến lời gọi không còn hợp lệ, mã nguồn cũ không còn tương thích.

Điều cần quan sát là **mã nguồn được biên dịch lại**. Một chương trình đã biên dịch từ trước có thể vẫn chạy với thư viện mới dù mã nguồn của nó không còn biên dịch được; trường hợp đó liên quan đến tương thích nhị phân, sẽ được phân biệt ở phần tiếp theo.

Tương thích mã nguồn không có nghĩa mọi file cũ đều tự động chạy đúng trong mọi môi trường mới. Kết quả biên dịch còn phụ thuộc vào phiên bản JDK, mức ngôn ngữ Java, API nền tảng được phép sử dụng, dependency, compiler option, annotation processor và cấu hình build.

## 2. Phân biệt tương thích mã nguồn với các loại tương thích khác

Trong một đợt nâng cấp, cần phân biệt ít nhất ba khái niệm:

| Loại tương thích | Câu hỏi cần trả lời | Điều được kiểm tra |
|---|---|---|
| Tương thích mã nguồn (*source compatibility*) | Mã nguồn cũ có biên dịch được với phiên bản mới không? | Cú pháp, kiểu dữ liệu, API, overload, dependency và cấu hình compiler |
| Tương thích nhị phân (*binary compatibility*) | Bytecode đã biên dịch trước đây có liên kết và chạy được với thư viện mới không? | Tên lớp, tên phương thức, descriptor, trường, constructor và cấu trúc liên kết ở mức JVM |
| Tương thích hành vi (*behavioral compatibility*) | Chương trình có tiếp tục tạo ra kết quả và tác dụng như trước không? | Kết quả, ngoại lệ, thứ tự xử lý, mặc định, thời điểm thực thi và các tác dụng phụ |

Ba loại này có liên quan nhưng không thay thế cho nhau.

- Mã nguồn có thể biên dịch thành công nhưng hành vi thay đổi vì phiên bản mới đổi giá trị mặc định hoặc thuật toán.
- Bytecode cũ có thể chạy được với thư viện mới, trong khi biên dịch lại mã nguồn cũ thất bại vì một overload mới làm lời gọi trở nên mơ hồ.
- Mã nguồn có thể được sửa để biên dịch với API mới, nhưng bytecode cũ vẫn không liên kết được vì descriptor của phương thức đã thay đổi.

Do đó, một kế hoạch migration đầy đủ cần kiểm tra riêng việc biên dịch lại, khả năng liên kết của binary cũ khi cần duy trì binary compatibility, và hành vi khi chạy.

## 3. Những yếu tố quyết định khả năng tương thích mã nguồn

### 3.1. Phiên bản ngôn ngữ Java và compiler

Mỗi phiên bản Java bổ sung cú pháp, quy tắc ngôn ngữ và khả năng mới. Một compiler mới thường có thể biên dịch mã dùng mức ngôn ngữ cũ, nhưng điều đó còn phụ thuộc vào tùy chọn build.

Ví dụ, mã có thể dùng `var` trong local variable từ Java 10 trở lên:

```java
var names = List.of("An", "Bình", "Chi");
```

Nếu dự án yêu cầu biên dịch với mức ngôn ngữ Java 8, đoạn mã này không hợp lệ. Ngược lại, mã Java 8 thông thường vẫn có thể được biên dịch bằng JDK mới nếu compiler được cấu hình để chấp nhận mức phát hành Java 8 và các API được sử dụng thuộc phạm vi Java 8.

Vì vậy cần tách biệt hai câu hỏi:

1. Compiler có hiểu cú pháp và quy tắc ngôn ngữ mà mã nguồn sử dụng không?
2. Mã nguồn có chỉ gọi những API tồn tại trong phiên bản Java mục tiêu không?

Chỉ đặt mức `source` và `target` chưa chắc đã trả lời đầy đủ câu hỏi thứ hai. Khi dùng JDK mới để tạo bytecode cho JDK cũ, nên dùng tùy chọn `--release` nếu compiler hỗ trợ. Tùy chọn này kết hợp mức ngôn ngữ, mức bytecode và tập API nền tảng tương ứng với release được chọn.

### 3.2. API công khai của thư viện

Đây là nguyên nhân thường gặp nhất khi biên dịch lại ứng dụng sau khi nâng cấp dependency. Mã nguồn bên ngoài có thể phụ thuộc vào:

- Tên package, class, interface, enum và annotation.
- Constructor và phương thức public hoặc protected.
- Tên phương thức, số lượng tham số, thứ tự tham số và kiểu tham số.
- Kiểu trả về, generic type và giới hạn kiểu (*type bounds*).
- Checked exception được khai báo.
- Hằng số, trường và mức truy cập.
- Kiểu lồng nhau, kiểu cha và interface mà một class triển khai.

Nếu thư viện xóa hoặc đổi tên một thành phần mà ứng dụng đang gọi, compiler không thể tìm thấy thành phần đó. Nếu thư viện thay đổi kiểu trả về, lời gọi có thể không còn gán được vào biến có kiểu cũ. Nếu thêm một overload, lời gọi trước đây có thể trở nên mơ hồ.

Không phải mọi thay đổi API đều làm mất tương thích. Chẳng hạn, thêm một phương thức độc lập thường không làm hỏng lời gọi hiện có. Tuy nhiên, cần xét toàn bộ quy tắc phân giải overload và kiểu dữ liệu ở vị trí gọi, thay vì chỉ nhìn vào việc API mới có thêm hay bớt thành phần.

### 3.3. Kiểu dữ liệu, generic và overload

Java kiểm tra kiểu dữ liệu tại thời điểm biên dịch. Vì vậy, thay đổi tưởng như nhỏ trong khai báo API có thể tác động đến mã gọi.

Một số tình huống cần chú ý:

- Đổi kiểu trả về từ `String` sang `CharSequence` có thể khiến code gán trực tiếp kết quả vào biến `String` không biên dịch được.
- Đổi tham số từ kiểu cụ thể sang kiểu tổng quát hơn có thể làm thay đổi overload được chọn.
- Thay đổi generic type có thể làm lộ lỗi kiểu mà compiler cũ không phát hiện hoặc thay đổi kiểu mà code gọi nhận được.
- Thêm overload có thể khiến một lời gọi vốn hợp lệ trở thành mơ hồ.
- Thay đổi visibility từ `public` hoặc `protected` sang mức hạn chế hơn có thể làm code bên ngoài không truy cập được.

Ví dụ về overload làm mã nguồn cũ mất khả năng biên dịch:

Phiên bản 1 của thư viện:

```java
public final class Messenger {
    private Messenger() {}

    public static void send(String message) {
        System.out.println(message);
    }
}
```

Ứng dụng sử dụng:

```java
Messenger.send(null);
```

Lúc này chỉ có một phương thức phù hợp nên compiler chọn `send(String)`. Sang phiên bản 2, thư viện bổ sung:

```java
public static void send(Integer code) {
    System.out.println(code);
}
```

`null` có thể gán cho cả `String` và `Integer`. Hai overload không có quan hệ kiểu con với nhau, nên compiler không thể chọn một phương thức cụ thể hơn. Lời gọi `Messenger.send(null)` trở thành lỗi *reference to send is ambiguous*.

Đây là một thay đổi có thể phá vỡ tương thích mã nguồn dù thư viện chỉ thêm phương thức. Nếu binary cũ đã được biên dịch trước đó, lời gọi của nó vẫn tham chiếu rõ descriptor của `send(String)`; vì phương thức đó vẫn tồn tại, binary có thể tiếp tục liên kết. Ví dụ này cho thấy source compatibility và binary compatibility phải được đánh giá riêng.

Ứng dụng có thể làm rõ ý định bằng cách ép kiểu:

```java
Messenger.send((String) null);
```

Tuy nhiên, nếu thư viện có nhiều người dùng, giữ API ít gây mơ hồ thường giúp quá trình nâng cấp dễ dàng hơn.

### 3.4. Checked exception

Checked exception là một phần của hợp đồng ở mức mã nguồn. Khi một phương thức bắt đầu khai báo thêm checked exception, code gọi có thể phải bổ sung `try-catch` hoặc khai báo `throws`.

Phiên bản 1:

```java
public String read(String path) {
    return loadFromCache(path);
}
```

Code gọi:

```java
String content = reader.read("config.txt");
```

Phiên bản 2:

```java
public String read(String path) throws IOException {
    return Files.readString(Path.of(path));
}
```

Khi biên dịch lại, code gọi cũ phải xử lý `IOException`:

```java
try {
    String content = reader.read("config.txt");
} catch (IOException exception) {
    // Xử lý lỗi đọc file phù hợp với ứng dụng.
}
```

Một chi tiết quan trọng: checked exception không nằm trong method descriptor mà JVM dùng để liên kết phương thức. Vì thế, việc thêm `throws IOException` không tự nó đổi descriptor của phương thức và bytecode cũ có thể vẫn liên kết. Tuy nhiên, hành vi chạy đã có thể thay đổi vì ngoại lệ mới có thể thoát ra trong tình huống trước đây không xảy ra. Đây là lý do cần kiểm tra cả source compatibility lẫn behavioral compatibility.

### 3.5. API của JDK và môi trường chạy

Khi nâng cấp JDK, không chỉ compiler thay đổi; tập API nền tảng và các module đi kèm cũng có thể thay đổi. Một số API bị đánh dấu deprecated, bị loại bỏ hoặc không còn được cung cấp sẵn trong JDK.

Ví dụ, từ Java 11, một số công nghệ Java EE/CORBA trước đây được đóng gói trong JDK đã bị loại khỏi JDK. Mã cũ tham chiếu các package như JAXB có thể không biên dịch nếu dự án không khai báo dependency tương ứng. Trong một số trường hợp, có thể tiếp tục dùng API đó bằng cách thêm thư viện độc lập phù hợp; trong trường hợp khác, cần chuyển sang API thay thế.

Không nên kết luận rằng một package không tồn tại chỉ vì JDK mới không còn đóng gói nó. Hãy kiểm tra classpath hoặc module path thực tế và dependency mà dự án cung cấp.

### 3.6. Dependency, annotation processor và mã được sinh tự động

Mã nguồn ứng dụng thường không chỉ phụ thuộc vào JDK. Một lần nâng cấp có thể đồng thời thay đổi:

- Thư viện trực tiếp và các dependency bắc cầu (*transitive dependencies*).
- Phiên bản plugin hoặc build tool.
- Annotation processor, compiler plugin và mã nguồn được sinh tự động.
- Module descriptor, classpath hoặc module path.
- Cấu hình kiểm tra warning, lint và quy tắc coi warning là lỗi.

Ví dụ, một annotation processor mới có thể sinh ra tên phương thức hoặc cấu trúc class khác phiên bản trước. Code ứng dụng vẫn không đổi nhưng việc biên dịch lại thất bại vì code được sinh ra đã thay đổi. Tương tự, nâng cấp một thư viện có thể kéo theo phiên bản dependency bắc cầu không tương thích với phần còn lại của ứng dụng.

Khi điều tra lỗi, hãy xác định đúng phiên bản thực tế mà build đã resolve. Khai báo phiên bản trực tiếp trong file cấu hình chưa đủ để chứng minh dependency được dùng lúc compile là phiên bản mong muốn.

## 4. Ví dụ: đổi API có thể làm mã nguồn cũ không biên dịch được

Giả sử phiên bản 1 của thư viện có API:

```java
public final class NameFormatter {
    private NameFormatter() {}

    public static String normalize(String value) {
        return value.trim();
    }
}
```

Ứng dụng gọi API:

```java
String name = NameFormatter.normalize(rawName);
```

Trong phiên bản 2, nhóm phát triển đổi tên phương thức:

```java
public final class NameFormatter {
    private NameFormatter() {}

    public static String canonicalize(String value) {
        return value.trim();
    }
}
```

Khi biên dịch ứng dụng cũ với phiên bản 2, compiler báo không tìm thấy phương thức `normalize(String)`. Đây là lỗi source compatibility: mã nguồn cũ vẫn nhắc đến một API không còn tồn tại.

Nếu muốn người dùng có thời gian chuyển đổi, thư viện có thể giữ phương thức cũ như một adapter:

```java
public final class NameFormatter {
    private NameFormatter() {}

    public static String canonicalize(String value) {
        return value.trim();
    }

    @Deprecated(since = "2.0", forRemoval = true)
    public static String normalize(String value) {
        return canonicalize(value);
    }
}
```

Code cũ tiếp tục biên dịch và phương thức cũ chuyển tiếp sang API mới. Annotation `@Deprecated` thông báo cho người dùng rằng họ nên chuyển đổi; `forRemoval = true` cho biết API có thể bị loại bỏ trong một phiên bản tương lai. Khi loại bỏ thật sự, nhà phát triển thư viện cần công bố rõ phiên bản và hướng dẫn migration.

Adapter chỉ phù hợp khi có thể duy trì cùng ý nghĩa và hợp đồng của API cũ. Nếu hành vi cũ không còn an toàn hoặc không thể mô phỏng, cần mô tả rõ thay đổi và cung cấp hướng chuyển đổi thay thế.

## 5. Cấu hình biên dịch để kiểm tra đúng phiên bản mục tiêu

Một phép thử tương thích chỉ có ý nghĩa khi compiler và API mục tiêu được cấu hình đúng. Dùng JDK mới không đồng nghĩa ứng dụng đã được kiểm tra cho mọi phiên bản Java cũ.

### 5.1. Dùng `javac --release`

Với JDK 9 trở lên, tùy chọn `--release` cho phép chỉ định release Java mục tiêu:

```bash
javac --release 11 -d out src/com/example/App.java
```

Lệnh trên yêu cầu compiler biên dịch mã theo Java 11 và giới hạn API nền tảng theo release đó. Nếu source dùng cú pháp mới hơn hoặc gọi API chỉ có ở JDK mới hơn, compiler sẽ báo lỗi.

`--release` kiểm soát API của nền tảng Java. Nó không tự kiểm tra tương thích của mọi thư viện bên thứ ba; dependency vẫn cần có phiên bản phù hợp với release mục tiêu.

### 5.2. Cấu hình Maven

Với Maven Compiler Plugin, có thể khai báo release trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Nên kiểm tra phiên bản Maven Compiler Plugin đang được sử dụng và JDK thực tế chạy Maven. Một cấu hình property không có tác dụng như mong muốn nếu plugin quá cũ hoặc build đang ghi đè compiler option ở nơi khác.

### 5.3. Cấu hình Gradle

Với Gradle Java plugin, có thể chọn toolchain và đặt release cho tác vụ biên dịch:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Toolchain xác định JDK dùng để chạy compiler. `options.release` xác định mức Java và API nền tảng mà source được phép sử dụng. Hai cấu hình giải quyết hai phần khác nhau của môi trường biên dịch.

Nếu chỉ đặt `sourceCompatibility` và `targetCompatibility`, compiler có thể tạo bytecode theo mức cũ nhưng vẫn nhìn thấy API của JDK mới đang chạy. Khi đó, code có thể biên dịch thành công nhưng lỗi lúc chạy trên JDK cũ vì gọi API không có trong môi trường đích. `options.release` giúp ngăn trường hợp này đối với API nền tảng Java.

## 6. Quy trình kiểm tra tương thích mã nguồn khi migration

Một quy trình có kiểm soát giúp xác định thay đổi nào thực sự làm mã nguồn cũ không biên dịch được.

### Bước 1: Ghi nhận baseline

Trước khi nâng cấp, lưu lại commit đang hoạt động và ghi nhận:

- JDK dùng để build và JDK dùng khi chạy.
- Mức Java source/API mục tiêu.
- Phiên bản Gradle hoặc Maven và các plugin liên quan.
- Dependency trực tiếp và phiên bản đã resolve của dependency bắc cầu.
- Các compiler option, annotation processor và profile build đang bật.

Baseline giúp tái hiện lỗi và xác định chính xác thành phần nào đã thay đổi.

### Bước 2: Xác định môi trường đích

Chốt JDK chạy compiler, release Java cần hỗ trợ, runtime thực tế và phiên bản dependency muốn nâng cấp. Không nên bắt đầu bằng việc thay nhiều phiên bản cùng lúc nếu chưa có lý do rõ ràng, vì khi đó rất khó quy kết nguyên nhân của lỗi.

### Bước 3: Biên dịch lại mã nguồn chưa sửa

Giữ nguyên source ở baseline và thay đổi môi trường sang cấu hình mới. Chạy một lần clean compile để phát hiện đầy đủ lỗi, thay vì chỉ build một module đã có output cũ.

Ví dụ với Gradle:

```bash
./gradlew clean compileJava
```

Với dự án nhiều module, cần bảo đảm các module liên quan đều được biên dịch. Một module có thể biên dịch độc lập nhưng thất bại khi được sử dụng cùng module khác do API hoặc dependency không đồng nhất.

### Bước 4: Phân loại lỗi compiler

Đọc lỗi đầu tiên theo chuỗi phụ thuộc và nhóm chúng theo nguyên nhân:

| Nhóm lỗi | Dấu hiệu thường gặp | Hướng điều tra |
|---|---|---|
| API bị xóa hoặc đổi tên | `cannot find symbol`, không tìm thấy package hoặc class | So sánh API cũ và mới; tìm API thay thế hoặc adapter |
| Thay đổi kiểu | `incompatible types`, lỗi generic hoặc conversion | Kiểm tra kiểu tham số, kiểu trả về và generic bounds |
| Overload mơ hồ | `reference to ... is ambiguous` | Xem các overload mới và kiểu biểu thức tại vị trí gọi |
| Checked exception | `unreported exception` | Xem khai báo `throws`, bổ sung xử lý lỗi phù hợp |
| API JDK không có | Không tìm thấy package hoặc method của nền tảng | Kiểm tra `--release`, JDK mục tiêu và dependency cung cấp API |
| Mã sinh tự động | Lỗi nằm trong generated source hoặc symbol do processor tạo | Kiểm tra phiên bản và cấu hình annotation processor |
| Dependency hoặc module | Không resolve được artifact, package không được export/read | Kiểm tra dependency graph, classpath và module path |

Không nên sửa hàng loạt theo thông báo lỗi mà chưa hiểu nguyên nhân. Một lỗi đầu nguồn có thể tạo ra nhiều lỗi tiếp theo; sửa đúng nguyên nhân gốc thường làm giảm đáng kể số lỗi còn lại.

### Bước 5: Chọn cách sửa theo hợp đồng

Với mỗi lỗi, xác định code nào sở hữu hợp đồng bị thay đổi:

- Nếu ứng dụng gọi API đã đổi, cập nhật call site sang API mới và kiểm tra ý nghĩa nghiệp vụ.
- Nếu thư viện được đội ngũ của mình phát triển, cân nhắc giữ adapter hoặc overload tương thích trong giai đoạn chuyển tiếp.
- Nếu dependency bắc cầu bị nâng cấp ngoài dự kiến, xem lại dependency constraint hoặc chọn phiên bản tương thích.
- Nếu lỗi đến từ mức Java mục tiêu, xác nhận yêu cầu runtime trước khi đổi compiler release.
- Nếu API cũ đã bị loại bỏ vì lý do bảo mật hoặc thiết kế, không khôi phục nó một cách máy móc; dùng API thay thế đã được hỗ trợ.

Không nên thêm `catch (Exception)` hoặc ép kiểu tùy tiện chỉ để làm compiler hết báo lỗi. Cách sửa phải giữ được hợp đồng và xử lý lỗi đúng với nghiệp vụ.

### Bước 6: Biên dịch lại toàn bộ và chạy kiểm thử

Sau khi sửa, chạy clean build cho tất cả module có liên quan, sau đó chạy unit test, integration test và các kiểm thử đặc trưng của ứng dụng. Kiểm tra cả luồng thành công, lỗi, dữ liệu biên và hành vi có phụ thuộc vào mặc định của JDK hoặc thư viện.

Nếu cần hỗ trợ binary compatibility, hãy lấy một consumer đã biên dịch bằng phiên bản thư viện cũ và kiểm tra việc liên kết/chạy nó với thư viện mới. Clean compile từ source không thay thế được phép thử này.

### Bước 7: Ghi nhận kết quả migration

Ghi lại phiên bản JDK, mức release, dependency đã nâng cấp, các API đã thay thế, thay đổi hành vi đã xác nhận và những giới hạn còn tồn tại. Thông tin này giúp các module hoặc nhóm khác thực hiện cùng đợt nâng cấp theo cách nhất quán.

## 7. Những sai lầm thường gặp

### Chỉ chạy build tăng dần

Build tăng dần có thể sử dụng output hoặc cache từ lần build trước. Nó không phải lúc nào cũng buộc mọi source được biên dịch lại với compiler và dependency mới. Khi kiểm tra migration, hãy dùng clean build trong môi trường đã xác định.

### Nhầm `source`/`target` với API mục tiêu

Đặt bytecode target thấp không tự động giới hạn toàn bộ API mà compiler nhìn thấy. Dùng `--release` hoặc cấu hình tương đương để kiểm soát API nền tảng.

### Cho rằng biên dịch thành công nghĩa là tương thích hoàn toàn

Compiler không thể chứng minh chương trình vẫn cho cùng kết quả, không phát sinh lỗi runtime hoặc không thay đổi hiệu năng. Những điều đó cần kiểm thử hành vi và kiểm thử trên môi trường chạy thực tế.

### Chỉ kiểm tra dependency trực tiếp

Một dependency bắc cầu có thể thay đổi khi nâng cấp thư viện khác. Hãy xem dependency graph đã resolve và kiểm tra classpath/module path của tác vụ compile.

### Sửa lỗi bằng ép kiểu hoặc bắt ngoại lệ rộng

Ép kiểu có thể che giấu thay đổi kiểu dữ liệu; bắt ngoại lệ quá rộng có thể biến lỗi thật thành trạng thái không rõ ràng. Trước khi sửa, cần hiểu hợp đồng mới và chọn cách xử lý phù hợp.

### Bỏ qua warning về API deprecated

Warning deprecated thường là tín hiệu về một lần loại bỏ trong tương lai. Hãy xác định API thay thế và lên kế hoạch chuyển đổi trước khi phiên bản tiếp theo xóa API đó.

## 8. Checklist cho một lần nâng cấp

Trước khi kết luận mã nguồn cũ tương thích với phiên bản mới, hãy xác nhận:

- [ ] Đã xác định JDK của compiler và runtime mục tiêu.
- [ ] Đã đặt đúng mức Java release và API nền tảng cần hỗ trợ.
- [ ] Đã ghi nhận phiên bản build tool, plugin và dependency đã resolve.
- [ ] Đã chạy clean compile trên source cũ trước khi sửa source.
- [ ] Đã biên dịch tất cả module và source được sinh tự động có liên quan.
- [ ] Đã xử lý lỗi API, kiểu dữ liệu, overload, checked exception và module/classpath.
- [ ] Đã rà soát warning deprecated và API có thể bị loại bỏ.
- [ ] Đã chạy unit test, integration test và kiểm thử hành vi trên runtime mục tiêu.
- [ ] Đã kiểm tra riêng binary compatibility nếu sản phẩm cần hỗ trợ binary đã biên dịch từ trước.
- [ ] Đã ghi lại thay đổi và giới hạn còn tồn tại.

## 9. Kết luận

Tương thích mã nguồn trả lời câu hỏi liệu source cũ có thể được biên dịch lại trong môi trường mới hay không. Kết quả phụ thuộc đồng thời vào ngôn ngữ Java, API của JDK, API thư viện, kiểu dữ liệu, overload, checked exception, dependency và cấu hình build.

Khi migration, hãy biên dịch lại source cũ trong môi trường đích đã xác định, phân loại lỗi theo nguyên nhân, sửa theo hợp đồng API và kiểm thử sau khi biên dịch. Việc này cho biết mức độ tương thích ở tầng mã nguồn; binary compatibility và behavioral compatibility vẫn cần được kiểm tra riêng khi yêu cầu của hệ thống bao gồm hai khía cạnh đó.
