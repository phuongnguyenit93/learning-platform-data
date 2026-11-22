# Ảnh hưởng của Class-Path, package sealing và JAR đa phiên bản

## Mục tiêu

Khi đóng gói một plugin Java thành JAR, mã nguồn biên dịch thành công vẫn chưa đảm bảo plugin được nạp hoặc hành xử đúng lúc chạy. Ba cơ chế ảnh hưởng trực tiếp đến điều đó là:

1. **Class path** xác định nơi JVM và class loader tìm lớp, tài nguyên và service descriptor.
2. **Package sealing** ràng buộc các lớp cùng một package phải đến từ một code source (thường là cùng JAR) khi được định nghĩa trong cùng class loader.
3. **Multi-release JAR (MR-JAR)** cho phép một JAR chứa các implementation khác nhau theo phiên bản Java Runtime.

Các cơ chế này giải quyết những vấn đề khác nhau. Class path không tự thực hiện cách ly plugin, sealing không phải sandbox bảo mật, còn MR-JAR không chọn phiên bản theo ứng dụng hay framework: nó chọn theo phiên bản Java Runtime.

## 1. Class path ảnh hưởng đến plugin như thế nào?

### 1.1. Tìm lớp và tài nguyên

Ở mô hình đơn giản dùng application class loader, lệnh:

\`\`\`bash
java -cp "app.jar:plugin.jar:api.jar" demo.host.Main
\`\`\`

cho phép tìm lớp và tài nguyên từ ba JAR trên class path. Trên Windows, dấu phân cách các entry là \`;\`, ví dụ:

\`\`\`powershell
java -cp "app.jar;plugin.jar;api.jar" demo.host.Main
\`\`\`

\`-cp\` và \`-classpath\` tương đương. Thông thường JVM lấy class path từ \`-cp\`, \`--class-path\`, hoặc biến môi trường \`CLASSPATH\` khi không có tùy chọn dòng lệnh tương ứng. Tên class cần nạp phải đúng package, có file \`.class\` tương ứng ở đường dẫn bên trong JAR và tất cả các dependency cần thiết phải nhìn thấy được từ class loader.

Ví dụ lớp \`demo.plugin.UppercasePlugin\` phải nằm ở:

\`\`\`text
plugin.jar
└── demo/plugin/UppercasePlugin.class
\`\`\`

Nếu plugin được phát hiện qua Java SPI, JAR còn phải có:

\`\`\`text
META-INF/services/demo.api.MessagePlugin
\`\`\`

và nội dung file này liệt kê tên đầy đủ của provider, chẳng hạn \`demo.plugin.UppercasePlugin\`. \`ServiceLoader\` đọc descriptor theo class loader được sử dụng; JAR có mặt trên đĩa nhưng không nằm trên class path hoặc trong class loader phù hợp sẽ không tự được phát hiện.

### 1.2. Thứ tự class path, phiên bản trùng và dependency

Nếu hai JAR chứa cùng một binary name, ví dụ đều chứa \`demo.util.Helper\`, hành vi phụ thuộc class loader và thứ tự tra cứu. Với application class loader điển hình, lớp tìm thấy trước trên class path có thể được nạp; class loader khác hoặc launcher đặc thù có thể có chính sách riêng. Không nên dựa vào thứ tự JAR làm cơ chế chọn phiên bản plugin.

Một ví dụ dễ xảy ra:

\`\`\`text
host.jar       → dùng thư viện util bản 2
plugin-old.jar → đóng gói lại util bản 1 cùng package
\`\`\`

Nếu cả hai phiên bản được đặt chung trong một class loader, bản mà JVM nạp có thể không khớp với bản dùng khi biên dịch. Lỗi thường thấy là \`NoSuchMethodError\`, \`NoClassDefFoundError\`, hoặc thay đổi hành vi khó nhận biết.

Các biện pháp:

- Định nghĩa API chung trong **một contract JAR** mà host và plugin cùng sử dụng, tránh đóng gói trùng contract dưới các class loader khác nhau.
- Khai báo và kiểm thử các dependency runtime của từng plugin. JAR thường không tự chứa dependency phụ.
- Với hệ thống cần nhiều phiên bản của cùng thư viện, cân nhắc class loader riêng cho plugin, module layer hoặc đổi namespace bằng shading có kiểm soát; đánh giá kỹ phần giao diện chung và tài nguyên.
- Kiểm chứng bằng \`jar --list --file plugin.jar\`, cây dependency của công cụ build, và quan sát class loading khi có lỗi (\`-Xlog:class+load=info\` trên HotSpot hiện đại).

### 1.3. Class-Path trong MANIFEST.MF

Ngoài class path từ dòng lệnh, manifest của JAR có thể chứa thuộc tính **\`Class-Path\`** để tham chiếu các JAR/phần đường dẫn khác theo quy tắc của cơ chế JAR manifest. Ví dụ:

\`\`\`text
Manifest-Version: 1.0
Main-Class: demo.host.Main
Class-Path: lib/api.jar lib/helper.jar
\`\`\`

Với JAR khởi chạy ở thư mục \`dist/\`, cách bố trí có thể là:

\`\`\`text
dist/
├── host.jar
└── lib/
    ├── api.jar
    └── helper.jar
\`\`\`

Chạy:

\`\`\`bash
java -jar dist/host.jar
\`\`\`

Đối với launcher \`java -jar\`, manifest \`Main-Class\` quyết định entry point; tùy chọn \`-cp\` do người dùng cung cấp không thay thế class path của ứng dụng khi đang dùng chế độ \`-jar\`. Manifest \`Class-Path\` giúp JAR tham chiếu thư viện phụ trợ được đặt đúng vị trí; đây là thông tin về các dependency được liệt kê, không phải lệnh tự quét toàn bộ thư mục plugin.

**Lưu ý:** \`Class-Path\` của manifest nhận danh sách các URL tương đối phân cách bằng dấu cách, không dùng \`:\` hoặc \`;\` giống \`-cp\`. Đường dẫn tương đối được giải quyết theo vị trí của JAR chứa manifest; có các hạn chế và quy tắc hợp lệ của JAR specification. Nếu chỉ cần chạy nhanh ứng dụng với thư viện phụ trợ, dùng \`java -cp\` hoặc launcher có kiểm soát thường rõ ràng hơn.

### 1.4. Wildcard class path

\`\`\`bash
java -cp "dist/host.jar:dist/lib/*" demo.host.Main
\`\`\`

\`dist/lib/*\` đưa các JAR trong thư mục đó vào class path theo cơ chế wildcard của launcher Java. Nó không quét đệ quy thư mục con; thứ tự liệt kê JAR không nên được coi là ổn định. Dùng wildcard tiện cho môi trường đơn giản nhưng không giải quyết xung đột dependency, version pinning hay khả năng cập nhật plugin khi JVM đã chạy.

## 2. Package sealing là gì?

### 2.1. Cơ chế và mục đích

Trong JAR manifest, thuộc tính \`Sealed: true\` đánh dấu package được **seal**. Khi class loader định nghĩa package từ JAR đó, các lớp bổ sung của cùng package trong cùng class loader phải có cùng code source được phép theo kiểm tra sealing. Điều này ngăn việc chia một package đã được seal giữa các JAR nguồn khác nhau.

Ví dụ không nên làm:

\`\`\`text
plugin-core.jar
└── com/example/plugin/core/Engine.class
    (package com.example.plugin.core đã seal)

plugin-extension.jar
└── com/example/plugin/core/Helper.class
    (cùng package, nhưng từ JAR khác)
\`\`\`

Khi cùng một class loader cố định nghĩa cả hai lớp, có thể xuất hiện \`SecurityException: sealing violation\`. Sealing kiểm soát nguồn định nghĩa lớp trong package; nó không ngăn plugin gọi API nguy hiểm, đọc file hay thực thi mã với quyền của process.

### 2.2. Manifest cho toàn JAR và từng package

Một manifest có thể seal mặc định cho các package trong JAR:

\`\`\`text
Manifest-Version: 1.0
Sealed: true
\`\`\`

Hoặc chỉ seal một package, bằng named section có đường dẫn package kết thúc bằng \`/\`:

\`\`\`text
Manifest-Version: 1.0

Name: com/example/plugin/internal/
Sealed: true
\`\`\`

Các dòng trống trong manifest phân tách main attributes và named sections, vì vậy chúng có ý nghĩa. Tên section sử dụng đường dẫn bằng dấu \`/\`, không dùng dấu \`.\`. Manifest được đóng gói trong \`META-INF/MANIFEST.MF\`.

Ví dụ tạo JAR từ class đã biên dịch bằng manifest tự viết:

\`\`\`bash
jar --create --file plugin.jar --manifest MANIFEST.MF -C build/classes .
\`\`\`

Không thay \`META-INF/MANIFEST.MF\` tùy tiện sau khi build; công cụ packaging có thể tạo thêm thông tin manifest và các section.

### 2.3. Những ảnh hưởng thực tế khi tách plugin

- Package nội bộ của plugin nên có namespace riêng, ví dụ \`com.acme.plugin.csv.internal\`, tránh dùng chung package nội bộ với host hoặc plugin khác.
- Nếu chủ ý chia package giữa nhiều JAR trong **cùng class loader**, sealing có thể khiến thiết kế đó thất bại. Cân nhắc gộp class thuộc package cần seal vào một artifact hoặc đổi package.
- Hai class loader có thể định nghĩa các package cùng tên độc lập; sealing được kiểm tra trong phạm vi định nghĩa package của loader. Tuy nhiên, các class được nạp từ loader khác nhau có thể không tương thích kiểu, kể cả cùng tên.
- Nếu package đã được định nghĩa là sealed, việc một JAR khác khai báo unsealed không làm nó tương thích; tính nhất quán của sealing và code source phải được đảm bảo trong cấu trúc nạp lớp.
- JPMS named modules có quy định package/module và split package riêng; không nên coi manifest sealing là cơ chế thay thế quy tắc module.

### 2.4. Ví dụ tối thiểu kiểm chứng sealing

Tạo cây source:

\`\`\`text
src-a/demo/shared/A.java
src-b/demo/shared/B.java
\`\`\`

Nội dung \`src-a/demo/shared/A.java\`:

\`\`\`java
package demo.shared;
public class A {
    public static String name() { return "A"; }
}
\`\`\`

Nội dung \`src-b/demo/shared/B.java\`:

\`\`\`java
package demo.shared;
public class B {
    public static String name() { return "B"; }
}
\`\`\`

Biên dịch hai JAR riêng và seal JAR A:

\`\`\`bash
mkdir -p build/a build/b
javac -d build/a src-a/demo/shared/A.java
javac -d build/b src-b/demo/shared/B.java
printf 'Manifest-Version: 1.0\nSealed: true\n' > seal.mf
jar --create --file a.jar --manifest seal.mf -C build/a .
jar --create --file b.jar -C build/b .
\`\`\`

Tệp \`TestSealing.java\`:

\`\`\`java
public class TestSealing {
    public static void main(String[] args) throws Exception {
        Class.forName("demo.shared.A");
        Class.forName("demo.shared.B");
    }
}
\`\`\`

Chạy (Linux/macOS):

\`\`\`bash
javac TestSealing.java
java -cp ".:a.jar:b.jar" TestSealing
\`\`\`

Khi cùng loader nạp \`A\` trước (định nghĩa package đã seal theo nguồn \`a.jar\`), sau đó cố định nghĩa \`B\` từ \`b.jar\`, chương trình lỗi với \`SecurityException\` do sealing violation. Không nên phụ thuộc vào nguyên văn thông báo lỗi hoặc stack trace vì khác nhau theo runtime. Nếu bỏ sealing hoặc chuyển lớp vào package khác, tình huống xung đột sealing này không còn.

Trên Windows, tạo file \`seal.mf\` bằng editor hỗ trợ UTF-8 và dòng mới chuẩn rồi dùng \`java -cp ".;a.jar;b.jar" TestSealing\`. Ví dụ shell phía trên sử dụng \`printf\` theo POSIX.

## 3. Multi-release JAR: cùng API, implementation tùy Java Runtime

### 3.1. Cấu trúc và cách chọn class

Multi-release JAR (JEP 238, từ Java 9) cho phép mã mặc định ở root và class thay thế dưới \`META-INF/versions/<N>/\`, với \`N\` là phiên bản Java ít nhất 9. Manifest phải có:

\`\`\`text
Manifest-Version: 1.0
Multi-Release: true
\`\`\`

Cấu trúc điển hình:

\`\`\`text
library.jar
├── META-INF/MANIFEST.MF
├── demo/feature/RuntimeFeature.class
└── META-INF/versions/
    ├── 11/demo/feature/RuntimeFeature.class
    └── 17/demo/feature/RuntimeFeature.class
\`\`\`

Ở Java 8, JVM dùng class ở root. Với Java 11, runtime hỗ trợ MR-JAR tìm implementation tại version 11 nếu có; Java 17 ưu tiên implementation version 17. Với runtime lớn hơn, class loader chọn version cao nhất **không vượt quá** phiên bản Java hiện tại. Nếu không tồn tại class override phù hợp, nó rơi về class thấp hơn hoặc root. Mô tả này áp dụng cho cơ chế đọc MR-JAR chuẩn của Java; tooling tự xử lý ZIP hoặc loader tùy chỉnh phải kiểm chứng có hỗ trợ MR-JAR hay không.

\`META-INF/versions/\` không tạo package độc lập ở runtime: các class được chọn có cùng binary name. Public/protected API của versioned class cần giữ hợp đồng tương thích với base, tránh để cùng JAR cho hành vi mà caller không thể dự đoán.

### 3.2. Khi nào dùng trong plugin?

Giả sử plugin hỗ trợ nhiều runtime nhưng có thể tối ưu xử lý trên Java mới:

- Root implementation dùng API Java cũ để giữ mức runtime nền.
- Versioned implementation dùng API tối ưu hoặc tiện ích của Java 11/17.
- Host gọi contract ổn định, không cần tự viết \`if (javaVersion >= 17)\` cho logic thay thế class.
- Một JAR có thể phân phối đến nhiều môi trường, giảm số artifact cần quản lý.

MR-JAR chỉ thay thế lớp/tài nguyên theo quy tắc của nền tảng. Nó không cho phép bytecode được biên dịch với target Java 17 chạy trên Java 11 nếu class Java 17 bị đặt nhầm ở root, và cũng không thay thế việc xác định version của contract API.

### 3.3. Ví dụ MR-JAR chạy được trên Java 17

Tạo hai bản của cùng class \`demo.feature.Message\`:

\`\`\`text
src/base/demo/feature/Message.java
src/java17/demo/feature/Message.java
\`\`\`

Base:

\`\`\`java
package demo.feature;
public class Message {
    public static String text() {
        return "base";
    }
}
\`\`\`

Java 17:

\`\`\`java
package demo.feature;
public class Message {
    public static String text() {
        return "java17";
    }
}
\`\`\`

Tệp \`Main.java\`:

\`\`\`java
import demo.feature.Message;
public class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
\`\`\`

Từ thư mục gốc ví dụ, chạy với JDK 17+:

\`\`\`bash
mkdir -p build/base build/v17 build/main
javac --release 8 -d build/base src/base/demo/feature/Message.java
javac --release 17 -d build/v17 src/java17/demo/feature/Message.java
jar --create --file feature.jar -C build/base . \
  --release 17 -C build/v17 .
javac --release 8 -cp feature.jar -d build/main Main.java
java -cp "build/main:feature.jar" Main
\`\`\`

Đầu ra trên Java 17:

\`\`\`text
java17
\`\`\`

Tùy chọn \`jar --release 17\` của JDK tạo phần versioned entry và cấu hình manifest \`Multi-Release: true\` tương ứng. Lệnh \`javac --release 8\` biên dịch root với API và bytecode tương thích Java 8. Với Java 8 runtime có thể chạy class base, miễn là app cũng không dùng API Java mới và runtime đọc được JAR đó; trên Java 11 (không có bản override 11), đầu ra là \`base\`. Không thể kiểm chứng Java 8/11 bằng một máy chỉ cài JDK 17; phải chạy trên runtime mục tiêu.

Để xem entry và manifest:

\`\`\`bash
jar --list --file feature.jar
jar --describe-module --file feature.jar
\`\`\`

Lệnh đầu phải cho thấy \`demo/feature/Message.class\`, \`META-INF/versions/17/demo/feature/Message.class\` và manifest. \`jar --describe-module\` hữu ích khi đánh giá thông tin module nhưng không thay cho việc kiểm tra manifest hoặc chạy trên từng JVM hỗ trợ.

### 3.4. Hệ quả đối với API, kiểm thử và phân tích

- Compiler, IDE, bytecode scanner, code coverage, shading, obfuscation và các công cụ build phải hiểu versioned entries; nếu không, chúng có thể quét nhầm, bỏ sót hoặc phá cấu trúc MR-JAR.
- Bản root và bản versioned phải giữ hợp đồng API ổn định; test trên **mỗi phiên bản Java được tuyên bố hỗ trợ**, không chỉ JDK build.
- Nếu plugin đang được nạp bởi class loader tùy chỉnh, xác minh loader dùng cách truy cập JAR có hỗ trợ multi-release. Truy cập file ZIP trực tiếp có thể thấy nhiều entry vật lý khác nhau thay vì class được chọn cho JVM hiện tại.
- Không đặt service descriptor vào versioned area với kỳ vọng SPI luôn đổi provider theo runtime: việc khám phá tài nguyên service cần được kiểm chứng riêng; thông thường giữ \`META-INF/services\` ở vị trí chuẩn, còn implementation versioned thay thế theo binary name.
- Cảnh giác class bytes versioned phụ thuộc class khác không có ở runtime tương ứng hoặc thiếu dependency runtime, khiến plugin thất bại dù manifest đúng.

## 4. Ba cơ chế tương tác ra sao?

| Tình huống | Cơ chế chi phối | Hệ quả thực tế |
|---|---|---|
| Plugin JAR nằm ngoài class path/class loader | Class path / ClassLoader | Host không tìm thấy lớp hoặc service provider |
| Hai plugin có class cùng tên trong chung loader | Tra cứu class path và quyền định nghĩa class | Có thể nạp nhầm implementation/version; cần tránh trùng lớp |
| Cùng package nằm ở hai JAR, một package đã seal | Package sealing | Có thể ném \`SecurityException\` do vi phạm code source |
| Một MR-JAR có class root + version 17 | Multi-release lookup | Java 17 chọn class version 17; runtime thấp hơn chọn bản phù hợp |
| MR-JAR được phát hành nhưng thiếu \`Multi-Release: true\` | Manifest / JAR processing | Versioned class không được dùng như lớp override chuẩn |
| Plugin dùng dependency Java 17 nhưng host chạy Java 11 | Runtime compatibility | Có thể gặp \`UnsupportedClassVersionError\` hoặc lỗi thiếu API |
| Host và plugin nạp contract bằng hai loader khác nhau | Class identity | Cùng tên interface vẫn có thể không ép kiểu được |

Một cách triển khai thực dụng là giữ API JAR chung nhỏ, quy định phạm vi version và class loader, đặt namespace package riêng cho mỗi plugin, và chỉ bật sealing hoặc MR-JAR khi thực sự có yêu cầu kiến trúc. Càng nhiều chính sách packaging, ma trận kiểm thử càng phải đầy đủ.

## 5. Quy trình chẩn đoán lỗi đóng gói

1. **Xác nhận bytecode và nội dung JAR.** Dùng \`jar --list --file <jar>\`, kiểm tra class đúng đường dẫn, manifest, provider descriptor và \`META-INF/versions/\`.
2. **Xác nhận runtime và launcher.** Dùng \`java -version\`, xem cách chạy với \`-jar\` hoặc \`-cp\`; kiểm tra dấu phân cách class path theo hệ điều hành và vị trí các JAR phụ thuộc.
3. **Quan sát class loader.** Với HotSpot, dùng \`-Xlog:class+load=info\` để xem class từ nguồn nào; trong mã chẩn đoán, \`SomeClass.class.getClassLoader()\` cho biết loader nạp class.
4. **Kiểm tra package sealing.** Đọc \`META-INF/MANIFEST.MF\`, tìm \`Sealed\` trong main section hoặc named package section; rà soát package bị chia giữa nhiều JAR và các nguồn code.
5. **Kiểm tra MR-JAR.** Xác nhận \`Multi-Release: true\`, đường dẫn versioned và class file version; chạy kiểm thử thực tế trên các Java Runtime được hỗ trợ.
6. **Kiểm tra compatibility và lỗi liên kết.** Đối chiếu dependency versions; \`ClassNotFoundException\` thường là nạp lớp theo tên không tìm thấy, \`NoClassDefFoundError\` có thể do lớp cần thiết không sẵn có ở runtime hoặc lỗi khởi tạo, \`NoSuchMethodError\` thường báo lệch binary API, còn \`UnsupportedClassVersionError\` báo class file mới hơn JVM có thể xử lý.

## 6. Checklist phát hành JAR plugin

- [ ] Các JAR host, contract và plugin được biên dịch với mức \`--release\` phù hợp; dependency runtime được cung cấp rõ ràng.
- [ ] Không nhúng bản contract trùng gây xung đột danh tính class giữa các loader.
- [ ] \`Class-Path\` manifest (nếu dùng) trỏ đến các dependency thực sự phân phối và hoạt động trên đường dẫn cài đặt.
- [ ] Không dựa vào thứ tự wildcard JAR để giải quyết phiên bản trùng.
- [ ] Sealing chỉ áp dụng cho package có ranh giới code source rõ ràng, không vô tình seal package chia nhiều JAR.
- [ ] MR-JAR có manifest và entry version đúng; phần root vẫn chạy trên Java nền được hỗ trợ.
- [ ] Kiểm thử plugin discovery, thiếu dependency, nhiều provider, lỗi sealing và JVM versions mục tiêu.
- [ ] Ghi rõ yêu cầu Java Runtime, API compatibility, class loader model và cách cài/gỡ plugin trong tài liệu triển khai.

**Ghi nhớ:** Class path quyết định **lớp được tìm ở đâu**, package sealing quyết định **lớp cùng package có được định nghĩa từ nguồn khác không**, còn MR-JAR quyết định **biến thể class nào được chọn theo Java Runtime**. Khi kết hợp chúng trong hệ thống plugin, phải kiểm tra cả ba ở runtime chứ không chỉ dựa vào build thành công.
