# Giới hạn phiên bản đích mà từng javac hỗ trợ

Khi một dự án Java cần hỗ trợ nhiều phiên bản JDK, nhóm phát triển thường muốn dùng một compiler mới để biên dịch mã nguồn nhưng vẫn tạo ra bytecode chạy được trên một runtime cũ hơn. Ví dụ, build bằng JDK 21 nhưng phát hành thư viện cho ứng dụng chạy trên Java 17, hoặc build bằng JDK 26 nhưng vẫn hỗ trợ runtime Java 8.

Khả năng này được gọi là *cross-compilation* hoặc biên dịch hướng tới một phiên bản nền tảng khác. Tuy nhiên, mỗi phiên bản `javac` chỉ hỗ trợ một tập phiên bản đích nhất định. Tập đó thay đổi theo JDK và theo tùy chọn được dùng. Không thể giả định rằng một compiler mới luôn biên dịch được cho mọi phiên bản Java cũ.

Điều cần nắm vững là sự khác nhau giữa `-source`, `-target` và `--release`; giới hạn thấp nhất/cao nhất của từng compiler; và cách xem chính xác danh sách target mà `javac` trên máy đang hỗ trợ.

## 1. Ba khái niệm cần phân biệt

### 1.1. Phiên bản source

`-source N` yêu cầu compiler chấp nhận cú pháp và quy tắc ngôn ngữ Java của release `N`.

Ví dụ, khi biên dịch với `-source 8`, mã nguồn phải tuân theo quy tắc ngôn ngữ Java 8. Các cú pháp chỉ xuất hiện từ Java 9 trở lên sẽ không được chấp nhận.

`-source` điều khiển ngôn ngữ đầu vào. Nó không tự bảo đảm rằng mọi API mà mã nguồn gọi đều tồn tại trên Java 8.

### 1.2. Phiên bản target

`-target N` yêu cầu `javac` sinh class file phù hợp với phiên bản JVM `N`.

Ví dụ:

```bash
javac -source 8 -target 8 Hello.java
```

Compiler chấp nhận cú pháp Java 8 và sinh bytecode có định dạng tương thích với JVM Java 8. Tuy nhiên, nếu mã nguồn gọi một API chỉ có từ Java 11, lệnh trên vẫn có thể biên dịch thành công khi compiler nhìn thấy API đó trong JDK đang dùng. Khi chạy trên Java 8, chương trình có thể lỗi vì thiếu method hoặc class.

### 1.3. Phiên bản release

`--release N` được giới thiệu từ JDK 9 theo JEP 247. Tùy chọn này kết hợp ba yêu cầu:

1. Chấp nhận cú pháp và quy tắc ngôn ngữ của Java release `N`.
2. Sinh class file có target tương ứng với release `N`.
3. Biên dịch dựa trên tập API công khai, được hỗ trợ và được tài liệu hóa của release `N`.

Ví dụ:

```bash
javac --release 8 -d out src/main/java/com/example/Hello.java
```

Nếu dùng JDK mới có hỗ trợ `--release 8`, compiler sẽ từ chối những API nền tảng chỉ xuất hiện sau Java 8. Đây là lý do `--release` thường là lựa chọn phù hợp nhất khi dùng một JDK mới để tạo artifact chạy trên JDK cũ.

Không được kết hợp `--release` với `-source` hoặc `-target` trong cùng một lần gọi `javac`.

## 2. Giới hạn chung của một javac

Có hai giới hạn chính:

- **Giới hạn trên:** compiler không thể tạo target cho một Java SE release mới hơn chính release mà compiler thuộc về. Muốn phát hành bytecode cho Java 26, cần một compiler hiểu Java 26, thường là `javac` của JDK 26 hoặc mới hơn.
- **Giới hạn dưới:** mỗi phiên bản `javac` chỉ giữ hỗ trợ cho một số release cũ. Các target quá cũ có thể bị deprecated rồi bị loại bỏ. Giới hạn thấp nhất khác nhau giữa JDK 8, 9, 11, 17, 25, 26 và các phiên bản khác.

Vì vậy, câu hỏi “javac hỗ trợ target từ Java nào đến Java nào?” phải luôn đi kèm phiên bản compiler và tùy chọn đang xét. Một máy có nhiều JDK cũng có thể cho kết quả khác nhau tùy đường dẫn `javac` được gọi.

## 3. Các mốc hỗ trợ theo phiên bản JDK

Bảng sau tổng hợp một số mốc tiêu biểu từ tài liệu JDK. Đây là các ví dụ theo từng thế hệ compiler, không phải một cam kết rằng mọi nhà cung cấp hoặc mọi bản build có cùng danh sách. Đặc biệt với các JDK mới, danh sách `--release` chính xác phải lấy từ `javac --help` của compiler đang dùng.

| Compiler | `-source` / `-target` | `--release` | Ghi chú |
|---|---|---|---|
| JDK 8 | `-source`: 1.3 đến 1.8; `-target`: 1.1 đến 1.8. | Không có tùy chọn này. | Muốn cross-compile cần dùng `-bootclasspath` và các thư viện nền tảng đúng phiên bản. |
| JDK 9 | Theo chính sách mới, hỗ trợ 6, 7, 8 và 9. | 6, 7, 8, 9. | `--release` được giới thiệu trong JDK 9. |
| JDK 10 | 6 đến 10; giá trị 6 bị deprecated và phát cảnh báo. | 6, 7, 8, 9, 10. | Tài liệu migration JDK 10 liệt kê source/target 6 đến 10. |
| JDK 11 | 6 đến 11; giá trị 6 bị deprecated và phát cảnh báo. | 6, 7, 8, 9, 10, 11. | Tài liệu Oracle JDK 11 liệt kê rõ tập release này. |
| JDK 17 | 7 đến 17. | Theo chính sách hỗ trợ release của compiler, kiểm tra bằng help. | Tài liệu migration của JDK 17 liệt kê source/target từ 7 đến 17. |
| JDK 25 | 9 đến 25; giá trị 8 bị deprecated và phát cảnh báo. | Release hiện tại và một số release cũ được hỗ trợ; xem help để biết danh sách chính xác. | Tài liệu Oracle JDK 25 nêu rõ giới hạn source/target và yêu cầu tra help cho `--release`. |
| JDK 26 | 9 đến 26; giá trị 8 bị deprecated và phát cảnh báo. | Release hiện tại và một số release cũ được hỗ trợ; xem help để biết danh sách chính xác. | Cần kiểm tra chính compiler/build đang chạy thay vì suy luận từ JDK khác. |
| JDK 27 | 9 đến 27; giá trị 8 bị deprecated và phát cảnh báo. | Release hiện tại và một số release cũ được hỗ trợ; xem help để biết danh sách chính xác. | Tài liệu migration JDK 27 tiếp tục nêu giới hạn source/target này. |

### 3.1. JDK 8: compiler cũ không có `--release`

JDK 8 `javac` có các mức source từ 1.3 đến 1.8 và target từ 1.1 đến 1.8. Các tùy chọn được dùng theo dạng:

```bash
javac -source 1.8 -target 1.8 Hello.java
```

JDK 8 không có `--release`. Khi cross-compile, chỉ đặt `-source` và `-target` là chưa đủ. Cần cung cấp đúng lớp nền tảng của phiên bản đích qua `-bootclasspath` (và các tùy chọn liên quan nếu cần). Nếu compiler nhìn thấy thư viện nền tảng của JDK 8 đang chạy, nó có thể vô tình cho phép gọi API không tồn tại trong phiên bản đích cũ hơn.

### 3.2. JDK 9: giới thiệu `--release`

JDK 9 giới thiệu `--release` thông qua JEP 247. Danh sách target được hỗ trợ gồm 6, 7, 8 và 9. JEP 182 cũng xác định rằng JDK 9 bỏ hỗ trợ source/target 5 trở xuống và áp dụng chính sách giới hạn các mức cũ.

Ví dụ:

```bash
javac --release 8 Hello.java
javac --release 9 Hello.java
```

Lệnh đầu tạo artifact theo nền tảng Java 8; lệnh sau tạo artifact theo Java 9. Không thể dùng `--release 10` với `javac` JDK 9 vì target 10 là phiên bản tương lai so với compiler.

### 3.3. JDK 10 và JDK 11

JDK 10 mở rộng danh sách `--release` tới 10; JDK 11 mở rộng tới 11. Tài liệu Oracle JDK 10 liệt kê source/target 6 đến 10, trong đó 6 đã deprecated và phát cảnh báo. Tài liệu Oracle JDK 11 liệt kê source/target 6 đến 11 và cũng đánh dấu 6 là deprecated.

Điều này minh họa nguyên tắc: compiler của một release mới thường bổ sung release đó vào tập target, nhưng không nhất thiết giữ mọi target cũ mãi mãi. Hãy đọc danh sách mà đúng phiên bản compiler công bố.

### 3.4. JDK 17

Tài liệu migration của JDK 17 liệt kê các giá trị `-source` và `-target` từ 7 đến 17. Đây là ví dụ cho thấy giới hạn thấp nhất đã thay đổi so với JDK 11.

Nếu một dự án cần Java 6, không thể mặc định rằng `javac` JDK 17 vẫn hỗ trợ target đó. Có thể cần compiler cũ hơn, hoặc phải thay đổi baseline runtime nếu yêu cầu nghiệp vụ cho phép.

### 3.5. JDK 25, JDK 26 và JDK 27

Tài liệu Oracle JDK 25, JDK 26 và JDK 27 cho biết các giá trị source/target được hỗ trợ từ release hiện tại trở xuống đến Java 9; Java 8 bị deprecated và phát cảnh báo. Khi nâng cấp compiler, một build trước đây dùng `-source 8 -target 8` có thể bắt đầu phát cảnh báo hoặc cần chuyển sang cấu hình được hỗ trợ theo chính sách compiler mới.

Đối với `--release`, tài liệu công bố nguyên tắc chung là release hiện tại và một số release trước đó, còn danh sách cụ thể nằm trong command-line help. Vì vậy, đừng tự suy ra danh sách `--release` từ bảng `-source/-target`; hãy kiểm tra từng tùy chọn riêng.

## 4. Xem danh sách target mà javac thực sự hỗ trợ

Đây là cách đáng tin cậy nhất để biết một compiler cụ thể chấp nhận release nào.

### 4.1. Kiểm tra đúng executable

Chạy:

```bash
javac -version
```

Nếu máy có nhiều JDK, hãy gọi compiler bằng đường dẫn đầy đủ để tránh nhầm lẫn:

```bash
"$JAVA_HOME/bin/javac" -version
"$JAVA_HOME/bin/javac" --help
```

Trên Windows PowerShell:

```powershell
& "$env:JAVA_HOME\bin\javac.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" --help
```

### 4.2. Đọc phần `--release`, `--source` và `--target`

```bash
javac --help
```

Trong help, tìm các dòng mô tả:

```text
--release <release>
    Compile for the specified Java SE release.
    Supported releases: ...

--source <release>
    Provide source compatibility with the specified Java SE release.
    Supported releases: ...

--target <release>
    Generate class files suitable for the specified Java SE release.
    Supported releases: ...
```

Đầu ra thực tế có thể rút gọn hoặc trình bày khác giữa các phiên bản. Hãy đọc cả ba dòng vì tập giá trị hỗ trợ của mỗi tùy chọn không nên được giả định là giống nhau.

Nếu compiler chỉ hiển thị dạng mô tả chung, có thể thử trực tiếp target cần dùng bằng một file Java nhỏ. Tuy nhiên, kết quả kiểm tra phải được thực hiện với chính compiler của pipeline build, không phải một compiler khác trên máy cá nhân.

### 4.3. Ghi lại kết quả trong CI

Để tránh việc một máy developer và CI dùng hai compiler khác nhau, nên ghi version và help output vào log khi cần chẩn đoán:

```bash
javac -version
javac --help
```

Nếu pipeline có nhiều toolchain, hãy in đường dẫn compiler và version tương ứng cho từng tác vụ compile. Khi một target bị loại khỏi JDK mới, log sẽ giúp xác định compiler nào đang từ chối cấu hình.

## 5. Vì sao `--release` an toàn hơn `-source` và `-target`?

Giả sử nhóm phát triển đang dùng JDK 21 nhưng cần phát hành thư viện chạy trên Java 8. Một lớp có thể viết như sau:

```java
public class TextHelper {
    public static String normalize(String value) {
        return value.strip();
    }
}
```

`String.strip()` chỉ có từ Java 11. Nếu dùng:

```bash
javac -source 8 -target 8 TextHelper.java
```

compiler có thể chấp nhận lời gọi `strip()` vì API đang được nhìn thấy là API của JDK 21. Bytecode đầu ra có thể mang class file version phù hợp Java 8, nhưng khi chạy trên Java 8 sẽ không tìm thấy method đó.

Nếu dùng:

```bash
javac --release 8 TextHelper.java
```

compiler chỉ cho phép dùng API nền tảng được công bố cho Java 8. Lời gọi `strip()` sẽ bị từ chối trong lúc biên dịch.

Đây là khác biệt cốt lõi:

| Cấu hình | Kiểm tra cú pháp ngôn ngữ | Kiểm soát bytecode target | Giới hạn API nền tảng theo target |
|---|---|---|---|
| `-source N` | Có | Không | Không |
| `-target N` | Không | Có | Không |
| `-source N -target N` | Có | Có | Không tự động |
| `--release N` | Có | Có | Có |

Nếu bắt buộc dùng `-source/-target`, phải cấu hình đúng tập lớp nền tảng bằng `-bootclasspath` cho target trước Java 9 hoặc `--system` cho target Java 9 trở lên. Cấu hình này phức tạp hơn và dễ sai hơn `--release`.

## 6. Class file version và phiên bản JVM đích

JVM dùng số major version trong class file để xác định định dạng bytecode. Một số mốc thường gặp:

| Java release | Class file major version |
|---:|---:|
| 8 | 52 |
| 9 | 53 |
| 10 | 54 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |
| 27 | 71 |

Ví dụ, class file major version 61 tương ứng Java 17. JVM Java 17 hiểu class file của Java 17 và các định dạng cũ được hỗ trợ; JVM Java 8 không hiểu class file major 61.

Có thể xem major version bằng:

```bash
javap -verbose -classpath out com.example.Hello
```

Trong kết quả, tìm `major version`. Lệnh này xác nhận định dạng class file đã tạo, nhưng không chứng minh chương trình chỉ dùng API có trong runtime đích. Để kiểm soát API nền tảng, vẫn cần `--release` hoặc cấu hình cross-compilation chính xác.

## 7. Giới hạn target và giới hạn đọc class file là hai việc khác nhau

Một `javac` mới có thể đọc và xử lý class file từ nhiều JDK cũ hơn, kể cả class file rất cũ. Điều đó không có nghĩa compiler có thể phát hành class file cho mọi release cũ.

Hãy phân biệt:

- **Input compatibility:** compiler có đọc được class file hoặc thư viện đã biên dịch từ phiên bản trước hay không.
- **Output target support:** compiler có thể sinh class file cho target release nào.
- **API compatibility:** mã nguồn có chỉ dùng API có mặt trong target release hay không.
- **Runtime compatibility:** ứng dụng và tất cả dependency có thực sự chạy được trên JVM đích hay không.

Một lần build thành công mới chỉ xác nhận một phần các điều kiện này. Cần chạy test trên runtime thấp nhất mà dự án cam kết hỗ trợ.

## 8. Khi target quá cũ không còn được hỗ trợ

Giả sử dự án cần phát hành Java 6 nhưng compiler mới không còn hỗ trợ `--release 6`. Có một số hướng xử lý:

1. **Dùng JDK compiler cũ phù hợp.** Đây là cách trực tiếp nếu dự án thật sự phải giữ baseline cũ và có thể duy trì toolchain tương ứng.
2. **Đánh giá lại baseline runtime.** Nếu người dùng và môi trường triển khai cho phép, nâng baseline lên một release còn được compiler và thư viện hỗ trợ.
3. **Tách artifact theo baseline.** Một nhánh hoặc artifact legacy có thể dùng toolchain cũ, còn artifact hiện đại dùng toolchain mới. Cần kiểm soát rõ API và dependency của từng biến thể.
4. **Dùng compiler khác có hỗ trợ mức ngôn ngữ cần thiết.** Chỉ chọn khi compiler đó có thể tạo bytecode và giới hạn API đúng với runtime mục tiêu; vẫn cần kiểm thử thực tế.

Không nên chỉ hạ số `-source` hoặc `-target` xuống một giá trị đã bị loại bỏ rồi tìm cách ép compiler chấp nhận. Điều đó không giải quyết được việc compiler không còn các mô hình ngôn ngữ hoặc API lịch sử cần thiết.

## 9. Cấu hình biên dịch đa phiên bản trong dự án

### 9.1. Biên dịch trực tiếp bằng javac

Để tạo artifact Java 17 bằng JDK mới:

```bash
javac --release 17 -d build/classes \
    src/main/java/com/example/App.java
```

Để tạo artifact Java 8 nếu compiler hiện tại hỗ trợ:

```bash
javac --release 8 -d build/classes \
    src/main/java/com/example/App.java
```

Hai lệnh dùng cùng compiler nhưng đặt hợp đồng ngôn ngữ, API và bytecode target khác nhau.

### 9.2. Maven

Với Maven Compiler Plugin, cấu hình `release` trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Đảm bảo phiên bản Maven Compiler Plugin đang dùng hỗ trợ thuộc tính này và Maven đang gọi đúng JDK/toolchain. Việc cài JDK 17 trên máy không tự bảo đảm Maven dùng JDK 17.

Nếu cần build với một JDK cụ thể, có thể dùng Maven Toolchains Plugin để chọn toolchain theo cấu hình dự án và máy build.

### 9.3. Gradle

Với Gradle, có thể đặt release cho tác vụ biên dịch Java:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
```

Hoặc cấu hình Java toolchain để chọn compiler:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
```

Trong ví dụ này, toolchain chọn compiler JDK 21; `options.release = 17` yêu cầu tạo artifact theo Java 17. Hai cấu hình có vai trò khác nhau: toolchain quyết định compiler nào chạy, release quyết định nền tảng đích.

## 10. Ma trận kiểm thử cho nhiều runtime

Nếu thư viện cam kết hỗ trợ Java 8, 17 và 21, chỉ build một lần thành công bằng JDK 21 chưa đủ. Nên kiểm thử trên từng runtime cam kết:

| Bước | Java 8 | Java 17 | Java 21 |
|---|---|---|---|
| Compile artifact | Có thể dùng `--release 8` nếu compiler hỗ trợ. | Có thể dùng `--release 17`. | Có thể dùng `--release 21`. |
| Kiểm tra class file | Major 52 | Major 61 | Major 65 |
| Unit test trên runtime | Có | Có | Có |
| Integration test | Có | Có | Có |
| Kiểm tra dependency | Phiên bản thư viện phải hỗ trợ Java 8. | Phiên bản thư viện phải hỗ trợ Java 17. | Phiên bản thư viện phải hỗ trợ Java 21. |

Trong CI, có thể dùng một compiler JDK mới để tạo artifact theo `--release` thấp nhất, sau đó chạy test trên từng JDK được hỗ trợ. Cũng nên có job build riêng trên các JDK LTS quan trọng nếu dự án cần phát hiện sớm thay đổi của compiler hoặc toolchain.

## 11. Các lỗi thường gặp và cách xử lý

### `error: release version N not supported`

Compiler không hỗ trợ target được yêu cầu. Kiểm tra `javac -version`, `javac --help` và đường dẫn compiler mà build tool thực sự gọi. Nếu target thấp hơn giới hạn của compiler, dùng toolchain cũ hơn hoặc điều chỉnh baseline sau khi đánh giá tác động.

### `Source option N is no longer supported`

Mức source đã bị loại bỏ khỏi compiler. Đừng giả định rằng một compiler mới hỗ trợ mọi source level cũ. Kiểm tra danh sách hỗ trợ và chính sách loại bỏ của JEP 182.

### Biên dịch thành công nhưng runtime báo `NoSuchMethodError` hoặc `NoClassDefFoundError`

Có thể build dùng `-source/-target` nhưng không giới hạn API nền tảng, hoặc một dependency bên ngoài được biên dịch cho Java mới hơn. Dùng `--release`, kiểm tra bytecode của dependency và chạy test trên runtime thấp nhất.

### `UnsupportedClassVersionError`

JVM đang chạy không hỗ trợ major version của class file. Kiểm tra major version bằng `javap -verbose`, xác định target đã dùng và kiểm tra runtime thực tế của tiến trình.

### IDE build được nhưng CI thất bại

IDE và CI có thể dùng compiler khác nhau hoặc phiên bản Maven/Gradle khác nhau. In đường dẫn `javac`, `javac -version`, cấu hình toolchain và release trong log của cả hai môi trường.

## 12. Quy trình xác định target phù hợp

1. **Xác định runtime thấp nhất cần hỗ trợ.** Đây là yêu cầu sản phẩm và môi trường triển khai, không phải quyết định tùy ý của compiler.
2. **Chọn compiler/toolchain.** Dùng JDK đủ mới để hỗ trợ ngôn ngữ và API mà dự án cần, nhưng phải kiểm tra target cũ có còn được hỗ trợ.
3. **Đọc danh sách target thực tế.** Chạy `javac --version` và `javac --help` từ đúng executable.
4. **Ưu tiên `--release`.** Dùng nó để đồng bộ source language, class file và API nền tảng.
5. **Kiểm tra dependency ngoài.** Mỗi thư viện phải hỗ trợ runtime thấp nhất; `--release` không tự kiểm soát bytecode của tất cả JAR phụ thuộc.
6. **Kiểm tra bytecode.** Dùng `javap -verbose` để xác nhận class file major version.
7. **Chạy test trên runtime thấp nhất.** Kiểm thử cả unit, integration, service loading, reflection và các đường chạy phụ thuộc môi trường.
8. **Ghi nhận toolchain trong CI.** Log JDK, compiler, release target và phiên bản plugin build để có thể tái hiện kết quả.

## 13. Những nguyên tắc cần nhớ

- Compiler chỉ tạo target cho release mà nó hỗ trợ; không thể tạo bytecode của một Java release tương lai.
- Giới hạn thấp nhất thay đổi theo phiên bản `javac` và có thể bị nâng lên khi target cũ bị loại bỏ.
- `-source` kiểm soát cú pháp; `-target` kiểm soát định dạng class file; hai tùy chọn này không tự giới hạn API nền tảng.
- `--release` là lựa chọn nên ưu tiên từ JDK 9 khi cần cross-compile.
- `--release` chỉ nhận một tập release được compiler hỗ trợ; xem `javac --help` để biết danh sách chính xác.
- Không kết hợp `--release` với `-source` hoặc `-target`.
- Đọc được class file cũ không đồng nghĩa có thể phát hành class file cho mọi target cũ.
- Compile thành công không thay thế kiểm thử trên runtime thấp nhất và kiểm tra dependency bên ngoài.

## Tài liệu tham khảo

- [JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): giới thiệu `--release` trong JDK 9.
- [JEP 182 — Policy for Retiring javac -source and -target Options](https://openjdk.org/jeps/182): chính sách loại bỏ các mức source/target cũ.
- [Oracle JDK 8 javac Tool Reference](https://docs.oracle.com/javase/8/docs/technotes/tools/unix/javac.html): danh sách source và target của compiler JDK 8.
- [Oracle JDK 9 Preparing for Migration](https://docs.oracle.com/javase/9/migrate/): chính sách “one plus three back” và việc giới thiệu `--release`.
- [Oracle JDK 10 Migration Guide](https://docs.oracle.com/javase/10/migrate/toc.htm): giới hạn source/target và release của JDK 10.
- [Oracle JDK 11 javac Tool Reference](https://docs.oracle.com/en/java/javase/11/tools/javac.html): các target `--release` được JDK 11 hỗ trợ.
- [Oracle JDK 17 Preparing for Migration](https://docs.oracle.com/en/java/javase/17/migrate/preparing-migration.html): giới hạn source/target của JDK 17.
- [Oracle JDK 26 Preparing for Migration](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html): chính sách source/target và khuyến nghị dùng `--release` trên JDK 26.
- [Oracle JDK 26 javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): cú pháp và giới hạn của các tùy chọn compiler.
- [Oracle JDK 27 Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html): giới hạn source/target của JDK 27.

## Kết luận

Phiên bản đích mà `javac` hỗ trợ phụ thuộc vào phiên bản compiler và tùy chọn biên dịch. JDK 8 chưa có `--release`; từ JDK 9, `--release` giúp đồng bộ quy tắc ngôn ngữ, bytecode và API nền tảng. Các target cũ dần bị deprecated hoặc loại bỏ, vì vậy hãy kiểm tra `javac --help` của đúng toolchain đang chạy. Khi build đa phiên bản, cần kết hợp `--release`, kiểm tra dependency bên ngoài, xác nhận class file và chạy test trên runtime thấp nhất mà sản phẩm cam kết hỗ trợ.
