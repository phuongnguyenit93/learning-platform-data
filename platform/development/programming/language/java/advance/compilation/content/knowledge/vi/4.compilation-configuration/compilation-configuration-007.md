# Phân loại tùy chọn chuẩn, mở rộng và nội bộ của `javac`

`javac` là công cụ biên dịch mã nguồn Java thành class file. Ngoài danh sách tệp `.java`, lệnh `javac` nhận các **tùy chọn (options)** để chọn phiên bản ngôn ngữ, API nền tảng, đường dẫn phụ thuộc, nơi xuất bytecode, cảnh báo, annotation processing, chẩn đoán và hành vi của trình biên dịch.

Cần phân biệt ba nhóm: **standard (chuẩn)**, **extra/extended (mở rộng)** và **internal/hidden (nội bộ hoặc ẩn)**. Cách phân loại phản ánh giao diện của công cụ và mức độ công bố, **không thể suy ra hoàn toàn từ số dấu gạch hoặc tiền tố của option**.

## 1. Bức tranh tổng quan

| Nhóm | Cách tìm | Mục đích và mức độ sử dụng | Ví dụ |
| --- | --- | --- | --- |
| **Standard** | `javac --help`; phần *Standard Options* trong manual của đúng JDK | Giao diện CLI chính để cấu hình những lần biên dịch thông thường; có tài liệu công khai, dùng trong script và build tool | `--release 17`, `-d out`, `-cp libs/api.jar`, `-encoding UTF-8`, `-g`, `-Werror` |
| **Extra / extended** | `javac --help-extra` hoặc `javac -X`; phần *Extra Options* | Tùy chọn nâng cao cho diagnostics, lint, xử lý annotation, plugin, điều chỉnh module; được mô tả công khai nhưng có thể có sự khác biệt giữa release | `-Xlint:unchecked`, `-Xdiags:verbose`, `-XprintRounds`, `-Xmaxerrs 50`, `--add-exports` |
| **Internal / hidden** | Thường không được liệt kê bởi cả hai màn hình help; chỉ xác nhận được từ implementation hay tài liệu chuyên biệt | Phục vụ thử nghiệm/debug/phát triển compiler; không có bảo đảm tương thích ở cấp giao diện CLI công khai | Họ `-XD...` trong OpenJDK `javac`; các tùy chọn khác được implementation đánh dấu hidden |

**Lưu ý về chữ “chuẩn”:** “standard option của `javac`” là cách nhóm tùy chọn của công cụ trong JDK. Điều đó không có nghĩa từng cờ đều được Java Language Specification yêu cầu mọi compiler bên thứ ba phải triển khai. Ngược lại, “extra” không có nghĩa là “bí mật”: nhiều cờ mở rộng có mục tài liệu chính thức và được dùng thường xuyên trong kiểm tra mã.

Trong nguồn OpenJDK, các option được phân loại theo các nhãn `STANDARD`, `EXTENDED`, `HIDDEN`. Đây là chi tiết để hiểu cấu trúc giao diện của `javac` OpenJDK; mã nguồn nội bộ của compiler tự nó không trở thành API ổn định.

## 2. Tra cứu nhóm tùy chọn ngay trên máy

Dùng chính compiler mà dự án thực sự chạy:

```sh
javac -version
javac --help
javac --help-extra
javac --help-lint
```

- `javac -version` cho biết phiên bản thực tế. Một lệnh trong terminal, IDE và CI có thể trỏ đến ba JDK khác nhau.
- `javac --help`, cũng có các alias `-help`/`-?`, hiển thị **standard options**.
- `javac --help-extra` hoặc `javac -X` hiển thị **extra options** được công cụ công bố.
- `javac --help-lint` liệt kê các **lint keys** hợp lệ cho `-Xlint` trên đúng bản JDK.

Ví dụ:

```text
javac -X
```

Lệnh trên chỉ **in trợ giúp** về extra options; nó **không bật tất cả cờ `-X`**. Còn:

```text
javac -Xlint:unchecked Example.java
```

là yêu cầu compiler kiểm tra nhóm cảnh báo `unchecked` đối với nguồn. Không được đánh đồng `-X` đứng một mình với `-Xlint` hoặc `-Xdiags`.

Tên cờ và hỗ trợ có thể thay đổi giữa release, nên khi một cờ không được nhận diện, cần đối chiếu **version**, màn hình help và tài liệu theo JDK đang dùng trước khi sửa cấu hình build.

## 3. Nhóm standard: thiết lập những gì được biên dịch và xuất ra

| Nhóm công việc | Tùy chọn standard thường dùng | Ý nghĩa |
| --- | --- | --- |
| Target nền tảng | `--release 17`; `--source 17`; `--target 17` | Giới hạn API nền tảng, cú pháp nguồn hoặc class-file version theo phạm vi từng cờ |
| Đầu ra | `-d out`, `-s generated`, `-h headers` | Nơi tạo class files, generated sources, native headers |
| Phụ thuộc | `--class-path path` / `-cp path`, `--source-path path` | Nơi tìm lớp/JAR và nguồn phụ thuộc |
| Named modules | `--module-path path`, `--module-source-path path`, `--module name` | Khai báo môi trường và chế độ biên dịch module |
| Đọc nguồn/debug | `-encoding UTF-8`, `-g`, `-g:none` | Encoding của source và metadata phục vụ debug |
| Cảnh báo | `-Werror`, `-nowarn` | Quyết định warning có làm build fail hoặc có được hiển thị hay không |
| Annotation processing | `-processor name`, `--processor-path path`, `-proc:none` | Khai báo và kiểm soát processor |
| Metadata reflection | `-parameters` | Ghi tên formal parameters để reflection đọc được |
| Tiện ích CLI | `--help`, `--version`, `@argfile` | Trợ giúp, phiên bản, nạp đối số từ file |

Các cờ là thành phần của một lệnh; **tên tệp nguồn** như `src/demo/Main.java` là operand, không phải option. Không nên đưa mọi chuỗi sau `javac` vào danh sách cờ.

### Chọn Java target: `--release` khác `--source` và `--target`

- `--source N`: cho phép/kiểm tra cú pháp và tính năng ngôn ngữ phù hợp mức Java `N`.
- `--target N`: chọn phiên bản class file hướng tới.
- **`--release N`**: kết hợp giới hạn cú pháp, class file target và **API nền tảng được hỗ trợ** cho Java `N`, khi compiler cho phép target đó.

Ví dụ trên JDK hỗ trợ Java 17:

```sh
javac --release 17 -encoding UTF-8 -d out src/demo/Main.java
```

Đây thường là lựa chọn đúng nếu sản phẩm cần chạy trên Java 17. Chỉ viết `-source 17 -target 17` trong một JDK mới hơn có thể vô tình cho phép gọi API chỉ xuất hiện ở bản JDK mới hơn. `--release` không tự đảm bảo các thư viện bên ngoài hay môi trường runtime của ứng dụng tương thích: cần kiểm chứng riêng.

**Không đặt `--release` cùng `--source`/`--target`** trong một lời gọi `javac`. Compiler cũng không bắt buộc hỗ trợ mọi số release tưởng tượng; xem những target được bản JDK đó liệt kê.

### `-Werror` và `-nowarn` là standard, dù liên quan warning

`-Werror` coi warning xuất hiện là lỗi của quá trình biên dịch. `-nowarn` tắt cảnh báo theo cơ chế được tài liệu hóa (tương đương `-Xlint:none`). Trong khi đó các **key** `-Xlint` lại thuộc nhóm extra. Hai loại tùy chọn có thể phối hợp: `-Xlint` chọn loại cảnh báo, `-Werror` làm build thất bại khi warning xuất hiện.

### `-d`, `-s` và `-h` có mục tiêu khác nhau

`-d out` xuất `.class` vào cây thư mục theo package, `-s generated` dành cho mã nguồn sinh bởi annotation processor, `-h headers` dành cho native headers khi được yêu cầu. `-d` không có nghĩa `javac` tự tạo JAR hay copy toàn bộ resource.

## 4. Nhóm extra: chẩn đoán và tác vụ chuyên sâu

| Option mở rộng | Tác dụng | Trường hợp dùng |
| --- | --- | --- |
| `-Xlint` | Bật các lint warnings được compiler khuyến nghị | Kiểm tra chất lượng |
| `-Xlint:unchecked` | Cảnh báo thao tác generic chưa thể kiểm chứng đầy đủ | Raw types, unchecked conversions |
| `-Xlint:deprecation` | Cảnh báo về cách dùng API deprecated | Di trú thư viện/API |
| `-Xlint:all` | Bật toàn bộ lint categories hợp lệ | Audit source khi đủ khả năng xử lý warnings |
| `-Xdiags:verbose` | Hiện diagnostics chi tiết hơn | Lỗi generic, overload và type inference |
| `-Xmaxerrs 50` | Giới hạn số lỗi in ra | Giảm log lỗi dây chuyền |
| `-Xmaxwarns 50` | Giới hạn số warning in ra | Giảm log build |
| `-XprintRounds` | In các vòng annotation processing | Debug processor/generation |
| `-XprintProcessorInfo` | In thông tin processor xử lý annotation | Phân tích processor đang hoạt động |
| `-Xprefer:source` | Ưu tiên source khi cả source và class có thể được tìm trong một số trường hợp | Điều tra implicit compilation |
| `-Xplugin:<name>` | Yêu cầu tải plugin `javac` tương ứng | Tích hợp công cụ phân tích nâng cao |
| `--add-exports`, `--add-reads`, `--patch-module` | Thay đổi khả năng truy cập/cấu hình module trong môi trường biên dịch | Tác vụ modular nâng cao |

**Hai quan sát cần nhớ:** Extra được tài liệu hóa chính thức, và **không phải mọi extra option đều bắt đầu bằng `-X`**: nhóm `--add-exports`/`--patch-module` cũng là extra ở tài liệu `javac`. Ngược lại, `-X` đứng một mình là yêu cầu hiển thị help, không phải cấu hình compile.

Các tùy chọn extra nên được thêm vì **mục tiêu rõ ràng**. Bật `-Xdiags:verbose` để hiểu lỗi khó, `-Xlint:unchecked` để phát hiện thao tác generic rủi ro; không thêm một tập cờ bí ẩn rồi không biết cờ nào tạo thay đổi.

### Ví dụ phối hợp standard và extra

```sh
javac --release 17 -encoding UTF-8 -Xlint:unchecked -Xlint:deprecation -Werror -d out src/demo/Main.java
```

Ở đây:

- `--release`, `-encoding`, `-Werror`, `-d` là **standard**.
- Hai `-Xlint:...` là **extra**, bật các cảnh báo mục tiêu.
- Nếu compiler phát cảnh báo phù hợp, `-Werror` có thể làm build thất bại; nếu không có lỗi hoặc warning, build có thể thành công.

`-Xlint` bổ sung chẩn đoán; lỗi cú pháp và kiểm tra kiểu cơ bản vẫn được thực hiện khi không dùng nó.

### `-Xdiags:verbose` làm gì?

```sh
javac --release 17 -Xdiags:verbose -d out src/demo/Main.java
```

Nó giúp hiển thị nhiều chi tiết hơn trong diagnostics; không tự sửa mã, đổi mục tiêu Java, chạy `main` hay bảo đảm bytecode khác khi mã hợp lệ.

### Annotation processing có cần extra để chạy không?

Không bắt buộc. Một processor có thể được cấu hình bởi standard options như `-processor`, `--processor-path` và `-proc:none`. `-XprintRounds`/`-XprintProcessorInfo` chỉ **quan sát** processing khi có processor phù hợp; `-Xplugin:<name>` cần plugin thực sự tồn tại. Việc khám phá processor mặc định thay đổi giữa các JDK; build cần cấu hình tường minh để dễ tái lập.

## 5. Nhóm internal/hidden: vì sao `-XD` là ranh giới khác?

Với implementation OpenJDK của `javac`, `-XD` là một ngõ vào bảng option nội bộ. Cú pháp biểu diễn ở mức implementation có thể là:

```text
-XDkey=value
-XDkey
```

Mã nguồn OpenJDK xử lý `-XDkey=value` bằng cách đưa cặp key/value vào bảng option nội bộ; dạng `-XDkey` có xử lý riêng để tạo một entry. **Đó là đặc điểm implementation**, không phải một giao diện có hợp đồng ổn định dành cho mọi chương trình Java hoặc mọi compiler.

Không nên suy ra “có cú pháp `-XD...` thì mọi key đều hợp lệ và có tác dụng”: một entry không được compiler đọc có thể không gây ảnh hưởng. Muốn hiểu một key cụ thể phải đọc **đúng mã nguồn, commit/build và phiên bản JDK** nơi nó được sử dụng.

### Rủi ro khi đưa cờ nội bộ vào dự án

1. **Thiếu cam kết tương thích:** tên, ý nghĩa hoặc pha compiler bị tác động có thể thay đổi mà không qua quy trình deprecation như API công khai.
2. **Có thể phá giả định build:** cờ thử nghiệm dùng để dừng pha, ghi log, thay đổi thứ tự xử lý hoặc kiểm tra internals có thể khiến output không đại diện build sản xuất.
3. **Phụ thuộc implementation:** một compiler khác, hoặc JDK của vendor khác, có thể không nhận ra hoặc hiểu cờ theo cách khác.
4. **Khó bảo trì:** người quản trị CI/IDE không tìm được cờ trong `--help-extra` và không biết vì sao nó có mặt.

Nếu đang điều tra lỗi chính compiler, có thể nghiên cứu internal options **trong môi trường riêng**, ghi rõ distribution/version/commit, đọc code tương ứng và loại bỏ cờ khỏi build chính sau khi điều tra. **Hidden** cũng không đồng nghĩa toàn bộ là `-XD`; implementation có thể đánh dấu ẩn những cờ debug khác.

### Bảng phân biệt “extra” và “internal”

| Câu hỏi | Extra (ví dụ `-Xlint`) | Internal (ví dụ `-XDkey`) |
| --- | --- | --- |
| Có trên `--help-extra`? | Thường có | Thường không |
| Có mô tả chính thức để dùng? | Có, theo bản JDK | Không phải hợp đồng người dùng thông thường |
| Nên dùng trong build? | Có thể, nếu cần và đã kiểm thử | Tránh, trừ nghiên cứu compiler có kiểm soát |
| Có thể thay đổi giữa JDK? | Có; phải kiểm tra version | Có, kể cả thay đổi chi tiết và không được công bố |
| Chỉ nhìn tiền tố là biết nhóm? | Không; có extra `--...` | Không; hidden còn nhiều dạng |

## 6. `-J`: standard option chuyển cờ cho JVM chạy compiler

`-J` là **standard launcher option của `javac`**, dùng để chuyển một đối số cho **JVM thực thi trình biên dịch**. Không nhầm với option điều khiển output Java hoặc extra option của compiler.

Ví dụ:

```sh
javac -J-Xmx512m --release 17 -d out src/demo/Main.java
```

- `-J-Xmx512m` yêu cầu launcher truyền `-Xmx512m` cho JVM của compiler (giới hạn heap tối đa theo cú pháp JVM).
- `--release 17` quyết định mức Java target.
- `-d out` quyết định nơi ghi class files.

Heap của JVM chạy **`javac`** khác heap của JVM chạy ứng dụng **`java`** sau đó. Nếu muốn đặt heap runtime, cấu hình riêng khi chạy: ví dụ `java -Xmx512m -cp out demo.Main`.

Cú pháp `-J` là viết liền option JVM: `-J-Xmx512m`. Theo manual `javac`, `-J` không được đặt trong file đối số `@argfile`. Với Compiler API hoặc build tool chạy compiler **trong cùng tiến trình**, cách cấu hình JVM cần phù hợp tiến trình chủ, chứ không mặc định `-J` sẽ được diễn giải như launcher CLI.

## 7. Thực hành Java 17: dùng cả cờ chuẩn và mở rộng

Tạo một tệp `src/demo/Main.java`:

```java
package demo;

import java.util.List;

public final class Main {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh");
        for (String name : names) {
            System.out.println(name);
        }
    }
}
```

Từ thư mục dự án, với JDK hỗ trợ Java 17:

```sh
javac --release 17 -encoding UTF-8 -d out -g -Xlint:all -Werror src/demo/Main.java
java -cp out demo.Main
```

Với mã trên, `javac` thành công và xuất `out/demo/Main.class`. Lệnh `java` in **stdout chính xác**:

```text
Lan
Minh
```

Phân nhóm trong ví dụ:

| Thành phần | Nhóm | Vai trò |
| --- | --- | --- |
| `--release 17` | Standard | Mục tiêu Java 17 |
| `-encoding UTF-8` | Standard | Đọc tệp nguồn UTF-8 |
| `-d out` | Standard | Nơi tạo class files |
| `-g` | Standard | Ghi debug information đầy đủ hơn |
| `-Xlint:all` | Extra | Bật lint warnings |
| `-Werror` | Standard | Cảnh báo phát sinh làm build thất bại |
| `src/demo/Main.java` | Operand | Tệp nguồn, không phải option |

**Không cần cờ internal `-XD`** cho quy trình này. Hai nhóm standard và extra cùng tồn tại trong một câu lệnh hợp lệ.

### Ví dụ thứ hai: cảnh báo generic có thể kiểm chứng

Tệp `src/demo/Warnings.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

public final class Warnings {
    public static void main(String[] args) {
        List raw = new ArrayList();
        raw.add("one");
        System.out.println(raw.get(0));
    }
}
```

Lệnh biên dịch:

```sh
javac --release 17 -Xlint:rawtypes,unchecked -d out src/demo/Warnings.java
java -cp out demo.Warnings
```

Compiler phát cảnh báo liên quan raw type và unchecked method invocation. Mẫu wording, số dòng và vị trí cảnh báo có thể khác theo JDK. Vì chưa có `-Werror`, quá trình biên dịch có thể vẫn thành công và stdout của chương trình là:

```text
one
```

Thêm `-Werror`:

```sh
javac --release 17 -Xlint:rawtypes,unchecked -Werror -d out src/demo/Warnings.java
```

Khi warning được phát ra, compilation thất bại. Không dùng việc `out/demo/Warnings.class` **còn tồn tại** để khẳng định lần biên dịch mới thành công, vì file từ lần trước có thể chưa bị xóa. Hãy kiểm tra **exit code** và diagnostics tương ứng với lần biên dịch đang xem.

## 8. Các quy tắc cú pháp dễ nhầm

### Alias và số lượng dấu gạch

`--class-path`, `-classpath` và `-cp` là các tên khác nhau của cơ chế classpath; `--source` và `-source` cũng có thể cùng được chấp nhận. Vì vậy, số lượng dấu gạch **không quyết định** option thuộc standard hay extra. Lệnh `--add-exports` trông giống các cờ standard bắt đầu bằng `--` nhưng được xếp extra.

Cú pháp truyền tham số phụ thuộc từng cờ. Với cờ dài phù hợp, có thể viết `--release 17` hoặc `--release=17`. Với `-Xlint:unchecked`, dấu hai chấm là một phần cú pháp. `-d out` cần đối số thư mục. Không hoán đổi tùy tiện `=`, `:` và khoảng trắng.

### Path separator khác theo hệ điều hành

Các path lists như classpath nhận dấu `;` trên Windows và dấu `:` trên Linux/macOS. Đây là chi tiết của hệ điều hành và option path, không phải khác biệt giữa standard với extra. Đường dẫn chứa khoảng trắng phải được quote đúng theo shell.

### Hỗ trợ option phụ thuộc phiên bản

Java 8 không có các option hệ module như Java 9 trở đi. `--release` chỉ nhận các release được compiler hỗ trợ. Một option có thể xuất hiện ở release này rồi thay đổi, bị hạn chế hoặc bị loại bỏ trong release khác. Việc `--help-extra` có liệt kê một cờ ở JDK 21 không bảo đảm mọi JDK khác chấp nhận nó với cùng ngữ nghĩa.

### `@argfile` không làm đổi phân loại

Tệp `compile.args` có thể chứa:

```text
--release 17
-encoding UTF-8
-d out
-Xlint:all
src/demo/Main.java
```

Gọi:

```sh
javac @compile.args
```

`@argfile` là cơ chế standard để truyền danh sách đối số dài. `-Xlint:all` **vẫn là extra** dù được đặt trong argument file. Đường dẫn bên trong file thường tương đối với **working directory của lời gọi compiler**, không phải vị trí của file đối số. `-J` không được chuyển bằng argument file theo đặc tả launcher.

Biến `JDK_JAVAC_OPTIONS` cũng có thể tự động bổ sung tham số cho lệnh `javac`. Khi hành vi compile khác giữa terminal và CI, kiểm tra biến môi trường này, `PATH`, `JAVA_HOME`, cấu hình toolchain và đối số thực tế trước khi quy lỗi cho bản thân compiler.

## 9. Cách chọn cờ trong dự án

1. **Nêu mục đích cần thiết:** tương thích Java 17, đường dẫn output rõ ràng, lỗi generic, hay debug annotation processing?
2. **Bắt đầu từ nhóm standard** phù hợp: `--release`, `-d`, `-encoding`, classpath/module path, cấu hình annotation processor.
3. **Bổ sung extra một cách có chủ đích:** `-Xlint` để rà warnings; `-Xdiags:verbose` khi cần hiểu lỗi; `-XprintRounds` khi điều tra processor.
4. **Tránh internal trên đường build chính:** chỉ dùng `-XD...` trong nghiên cứu compiler với phiên bản xác định và môi trường kiểm soát.
5. **Ghi nhận toolchain:** `javac -version`, các lệnh build thực tế, option tác động vào compiler và những option gửi cho JVM qua `-J`.
6. **Kiểm chứng đầu ra:** exit code, logs, class files mới, chạy thử trên JVM mục tiêu; không dựa vào artifact còn sót.

### Các nhận định sai thường gặp

- **“`-X...` luôn là option nội bộ.”** Sai: `-Xlint` và `-Xdiags` là extra có tài liệu công khai.
- **“Không có `-X` ở đầu thì chắc là standard.”** Sai: có các option `--...` thuộc nhóm extra.
- **“`javac -X` bật mọi lint.”** Sai: nó in help; `-Xlint` mới điều khiển lint.
- **“`-J-Xmx512m` làm ứng dụng sau khi compile có heap 512 MB.”** Sai: nó cấu hình JVM đang chạy compiler.
- **“`-XD...` là cách tốt để thay một option bị thiếu.”** Sai: khóa nội bộ không phải API công khai, không thể thay thế chức năng chưa được hỗ trợ.
- **“Extra option có tài liệu thì không bao giờ đổi.”** Sai: luôn kiểm tra manual và help của phiên bản toolchain thực tế.
- **“File `.class` vẫn còn nghĩa là mọi cờ compile đã hoạt động.”** Sai: file có thể là output của lần chạy trước.

## 10. Checklist để tự phân loại

- [ ] Đã chạy `javac -version` trên máy và CI?
- [ ] Đã đối chiếu `javac --help` và `javac --help-extra`?
- [ ] Với `-Xlint`, đã tra `javac --help-lint`?
- [ ] Đã phân biệt cờ được compiler đọc, cờ `-J` gửi cho JVM compiler và cờ của lệnh `java` chạy ứng dụng?
- [ ] Đã hiểu option ảnh hưởng source, bytecode, chẩn đoán hay processor?
- [ ] Đã tránh kết hợp `--release` với `--source`/`--target`?
- [ ] Có cờ hidden nào trong build cần loại bỏ hoặc xác minh bằng đúng version/source?
- [ ] Đã xác nhận exit code, warnings và class files của đúng lần biên dịch?

**Ghi nhớ:** Nhóm **standard** là giao diện cấu hình chính của `javac`; nhóm **extra** cung cấp tùy chọn nâng cao **được công bố**; nhóm **internal/hidden** phản ánh chi tiết triển khai và không có hợp đồng ổn định. Hãy phân nhóm dựa trên **trợ giúp/manual của đúng JDK**, thay vì suy đoán từ tiền tố.

### Tham khảo chính thức

- Oracle JDK 21, *The javac Command*: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — các mục *Standard Options*, *Extra Options*, *Command-Line Argument Files* và *Environment Variables*.
- OpenJDK `Option.java`: https://github.com/openjdk/jdk/blob/master/src/jdk.compiler/share/classes/com/sun/tools/javac/main/Option.java — mã implementation minh họa các nhóm `STANDARD`/`EXTENDED`/`HIDDEN` và lối vào `-XD`. Nhánh `master` có thể thay đổi theo thời gian; khi nghiên cứu phải đối chiếu mã đúng release.