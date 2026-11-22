# Custom doclet trong Javadoc

Doclet là thành phần quyết định Javadoc thu thập thông tin mã nguồn Java như thế nào và tạo ra đầu ra gì. Javadoc mặc định dùng Standard Doclet để tạo bộ tài liệu HTML. Khi cần định dạng tài liệu riêng, trích xuất API thành JSON/Markdown, tạo báo cáo kiểm tra hoặc tích hợp tài liệu vào một hệ thống khác, có thể viết **custom doclet** bằng API \`jdk.javadoc.doclet\`.

Custom doclet nhận mô hình ngôn ngữ của các package, class, method, field và comment Javadoc. Nó có thể duyệt các phần tử được chọn, đọc nội dung \`@param\`, \`@return\`, \`@throws\`, kiểm tra modifier và kiểu dữ liệu, rồi xuất kết quả theo định dạng do dự án quy định.

## 1. Doclet là gì?

Javadoc là công cụ đọc mã nguồn Java và documentation comments để tạo tài liệu. Doclet là phần mở rộng mà Javadoc gọi để xử lý mô hình tài liệu.

Trong lệnh thông thường:

~~~bash
javadoc -d docs -sourcepath src com.acme.api
~~~

Javadoc dùng Standard Doclet mặc định và tạo các trang HTML. Standard Doclet chịu trách nhiệm bố cục trang, navigation, index, liên kết API, stylesheet và nhiều tùy chọn định dạng.

Khi chỉ định custom doclet:

~~~bash
javadoc -doclet com.acme.tools.ApiDoclet -docletpath build/doclet
~~~

Javadoc nạp lớp doclet do dự án cung cấp và gọi API của nó. Custom doclet quyết định cách duyệt phần tử và tạo đầu ra. Nó có thể in báo cáo văn bản, tạo Markdown, JSON, XML hoặc HTML theo nhu cầu.

Một số trường hợp nên viết custom doclet:

- Tạo danh mục API công khai cho một thư viện nội bộ.
- Xuất chữ ký class/method thành JSON để công cụ khác tiêu thụ.
- Kiểm tra quy ước tài liệu, ví dụ method public phải có \`@param\` và \`@return\`.
- Tạo tài liệu theo mẫu riêng của tổ chức.
- Thu thập metadata từ annotation và documentation comments.
- Tích hợp Javadoc với hệ thống tài liệu hoặc quy trình build riêng.

Nếu chỉ muốn thêm cách hiển thị một tag Javadoc tùy chỉnh trong tài liệu HTML chuẩn, Taglet thường phù hợp hơn. Custom doclet thay thế bộ xử lý đầu ra; Taglet mở rộng cách Standard Doclet xử lý một loại tag.

## 2. API Doclet hiện đại

API doclet hiện đại nằm trong module JDK \`jdk.javadoc\`, package:

~~~java
jdk.javadoc.doclet
~~~

Interface trung tâm là:

~~~java
public interface Doclet
~~~

API này được cung cấp từ Java 9. Khi phát triển cho Java 17+, hãy dùng \`jdk.javadoc.doclet.Doclet\` và mô hình ngôn ngữ \`javax.lang.model\`. Các doclet cũ dựa trên package \`com.sun.javadoc\` thuộc API legacy và không nên dùng cho dự án mới.

Một custom doclet thường triển khai năm phương thức chính:

| Phương thức | Vai trò |
|---|---|
| \`init(Locale, Reporter)\` | Nhận locale và đối tượng báo cáo do Javadoc cung cấp. |
| \`getName()\` | Trả về tên doclet để hiển thị trong thông tin công cụ. |
| \`getSupportedOptions()\` | Khai báo các tùy chọn riêng mà doclet chấp nhận. |
| \`getSupportedSourceVersion()\` | Khai báo phiên bản cú pháp Java mà doclet hỗ trợ. |
| \`run(DocletEnvironment)\` | Thực hiện việc duyệt mô hình tài liệu và tạo đầu ra. |

Phương thức \`run\` trả về \`true\` nếu doclet hoàn thành thành công và \`false\` nếu xử lý thất bại. Không nên trả về \`true\` khi đã phát hiện lỗi nghiêm trọng khiến đầu ra không đáng tin cậy.

## 3. Vòng đời khi Javadoc chạy custom doclet

Quy trình tổng quát:

1. Javadoc đọc command-line options và xác định lớp doclet qua \`-doclet\`.
2. Công cụ nạp doclet từ \`-docletpath\` hoặc cơ chế module tương ứng.
3. Javadoc khởi tạo doclet bằng \`init\`, truyền locale và \`Reporter\`.
4. Công cụ truy vấn tên, source version và các option mà doclet hỗ trợ.
5. Javadoc phân tích source, resolve type và xây dựng mô hình tài liệu.
6. Javadoc gọi \`run\` với \`DocletEnvironment\`.
7. Doclet duyệt các phần tử được chọn, đọc comment và tạo đầu ra.
8. Doclet trả về trạng thái thành công/thất bại; Javadoc kết thúc với kết quả tương ứng.

Mô hình xử lý:

~~~text
Java source + Javadoc comments
             |
             v
          javadoc
             |
             v
      Load custom Doclet
             |
             v
       init(locale, reporter)
             |
             v
   Parse and select source elements
             |
             v
       DocletEnvironment
             |
             v
       run(environment)
             |
             v
   Inspect elements and comments
             |
             v
     Custom output / diagnostics
~~~

Doclet không tự thay thế compiler. Javadoc sử dụng compiler infrastructure để phân tích source và resolve kiểu. Doclet làm việc với mô hình đã được công cụ chuẩn bị.

## 4. Các thành phần quan trọng của Doclet API

### DocletEnvironment

\`DocletEnvironment\` là đối tượng đầu vào chính của \`run\`. Nó cung cấp:

- \`getSpecifiedElements()\`: các phần tử được chỉ định trực tiếp trong đầu vào Javadoc.
- \`getIncludedElements()\`: các phần tử được chọn để đưa vào tài liệu.
- \`isIncluded(element)\`: kiểm tra một phần tử có được đưa vào tài liệu hay không.
- \`isSelected(element)\`: kiểm tra phần tử có được chọn theo cấu hình xử lý hay không.
- \`getDocTrees()\`: truy cập cấu trúc documentation comments.
- \`getElementUtils()\`: công cụ tra cứu và phân tích phần tử Java.
- \`getTypeUtils()\`: công cụ phân tích quan hệ và phép biến đổi kiểu.
- \`getSourceVersion()\`: phiên bản source Java đang được xử lý.
- \`getJavaFileManager()\`: file manager được Javadoc sử dụng.

Nên dùng \`getIncludedElements()\` khi cần xử lý các phần tử đã được Javadoc chọn. Danh sách này chịu ảnh hưởng bởi tùy chọn như \`-public\`, \`-protected\`, \`-package\` hoặc \`-private\`.

### Element và TypeElement

Mô hình \`javax.lang.model.element\` đại diện cho cấu trúc Java:

| Interface | Đại diện |
|---|---|
| \`Element\` | Phần tử Java tổng quát. |
| \`PackageElement\` | Package. |
| \`TypeElement\` | Class, interface, enum, record hoặc annotation type. |
| \`ExecutableElement\` | Method hoặc constructor. |
| \`VariableElement\` | Field, parameter hoặc biến. |
| \`TypeParameterElement\` | Tham số kiểu generic. |
| \`ModuleElement\` | Module và các directive của module. |

\`Element.getEnclosedElements()\` trả về các phần tử được khai báo trực tiếp bên trong phần tử hiện tại. Ví dụ, với một \`TypeElement\`, danh sách có thể chứa field, constructor, method và nested type.

\`ElementFilter\` trong package \`javax.lang.model.util\` giúp lọc phần tử theo loại:

~~~java
ElementFilter.typesIn(elements)
ElementFilter.methodsIn(elements)
ElementFilter.fieldsIn(elements)
ElementFilter.constructorsIn(elements)
~~~

Các hàm này giúp tránh phải ép kiểu thủ công từng phần tử.

### Elements và Types

\`Elements\` cung cấp thao tác ở mức khai báo:

- Tra cứu package hoặc type theo tên.
- Lấy tên nhị phân của type.
- Lấy tất cả thành viên của một type, bao gồm thành viên kế thừa.
- Đọc documentation comment dạng văn bản.
- Kiểm tra phần tử có deprecated hay không.
- Lấy giá trị annotation đã áp dụng default.

\`Types\` cung cấp thao tác ở mức kiểu:

- Kiểm tra quan hệ subtype.
- Kiểm tra hai kiểu có tương đương hay không.
- Lấy kiểu sau type erasure.
- Kiểm tra phép gán hoặc chuyển đổi kiểu.
- Xử lý declared type, array type, wildcard và type variable.

Dùng \`Element\` để hỏi một khai báo là gì; dùng \`TypeMirror\` và \`Types\` để phân tích kiểu của khai báo đó. Không nên so sánh kiểu generic bằng cách chỉ so sánh chuỗi hiển thị nếu cần kiểm tra ngữ nghĩa chính xác.

### DocTrees và DocTree

\`DocTrees\` cung cấp cấu trúc cây cho documentation comments. Nó hữu ích khi doclet cần đọc tag hoặc phân tích nội dung thay vì chỉ lấy chuỗi văn bản.

Ví dụ:

~~~java
DocTrees docTrees = environment.getDocTrees();
DocCommentTree commentTree = docTrees.getDocCommentTree(element);
~~~

\`DocCommentTree\` biểu diễn phần mô tả, block tags và inline tags. Những loại tag thường gặp gồm:

- \`@param\`
- \`@return\`
- \`@throws\` hoặc \`@exception\`
- \`@since\`
- \`@deprecated\`
- \`@see\`
- \`{@link ...}\`
- \`{@code ...}\`

Có thể duyệt các node trong cây bằng visitor thuộc package \`com.sun.source.doctree\`. Khi cần kiểm tra chính xác tag \`@param\`, tên tham số và nội dung, xử lý cây thường an toàn hơn việc tìm chuỗi bằng regex.

## 5. Reporter và cách báo lỗi

Javadoc truyền \`Reporter\` vào \`init\`. Doclet dùng đối tượng này để gửi thông báo theo mức độ:

- \`Diagnostic.Kind.NOTE\`: thông tin.
- \`Diagnostic.Kind.WARNING\`: cảnh báo.
- \`Diagnostic.Kind.MANDATORY_WARNING\`: cảnh báo bắt buộc.
- \`Diagnostic.Kind.ERROR\`: lỗi.
- \`Diagnostic.Kind.OTHER\`: thông báo khác.

Ví dụ:

~~~java
reporter.print(
    Diagnostic.Kind.WARNING,
    element,
    "Public method is missing a documentation comment."
);
~~~

\`Reporter\` cũng cung cấp \`getStandardWriter()\` để in đầu ra thông thường và \`getDiagnosticWriter()\` để in thông tin chẩn đoán. Khi tạo báo cáo văn bản, nên dùng writer do Javadoc cung cấp thay vì ghi trực tiếp vào \`System.out\`; cách này giúp output tương thích hơn với môi trường chạy của công cụ.

Lỗi nội dung tài liệu nên được báo bằng \`Reporter\`, kèm phần tử liên quan nếu có thể. Điều đó giúp người dùng xác định chính xác class hoặc method cần sửa.

## 6. Custom option của doclet

Doclet có thể khai báo tùy chọn riêng thông qua \`getSupportedOptions()\`. Mỗi option triển khai \`Doclet.Option\`.

Một option cần cung cấp:

- \`getNames()\`: tên option, có thể có nhiều alias.
- \`getArgumentCount()\`: số đối số theo sau option.
- \`getParameters()\`: cách mô tả đối số trong help.
- \`getDescription()\`: mô tả chức năng.
- \`getKind()\`: nhóm option.
- \`process(option, arguments)\`: xử lý giá trị nhận được.

Ví dụ, doclet có thể hỗ trợ:

~~~bash
javadoc -doclet doclet.ApiSummaryDoclet \
  -docletpath build/doclet \
  --api-heading "Customer API" \
  --source-path src \
  -subpackages com.acme.api
~~~

Trong ví dụ, \`--api-heading\` là option riêng của doclet. \`Doclet.Option.Kind.OTHER\` phù hợp cho option do doclet tự định nghĩa; không dùng tên trùng với option mà Javadoc hoặc doclet khác đã sở hữu.

\`process\` trả về \`true\` khi giá trị được chấp nhận. Nếu đối số không hợp lệ, doclet có thể trả về \`false\` để Javadoc báo lỗi option. Với option có nhiều đối số, kiểm tra đủ số lượng và validate từng giá trị trước khi lưu vào trạng thái doclet.

## 7. Ví dụ hoàn chỉnh: tạo API summary doclet

Ví dụ sau viết một doclet nhỏ để liệt kê các type được Javadoc chọn, in documentation comment của class và chữ ký các method public/protected. Doclet có option \`--api-heading\` để thay đổi tiêu đề.

Cấu trúc thư mục:

~~~text
custom-doclet-demo/
└── src/
    ├── doclet/
    │   └── ApiSummaryDoclet.java
    └── com/
        └── acme/
            └── api/
                └── Greeting.java
~~~

Tệp \`src/doclet/ApiSummaryDoclet.java\`:

~~~java
package doclet;

import java.io.PrintWriter;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.TypeElement;
import javax.lang.model.util.ElementFilter;
import jdk.javadoc.doclet.Doclet;
import jdk.javadoc.doclet.DocletEnvironment;
import jdk.javadoc.doclet.Reporter;

public final class ApiSummaryDoclet implements Doclet {
    private Reporter reporter;
    private String heading = "API Summary";

    @Override
    public void init(Locale locale, Reporter reporter) {
        this.reporter = reporter;
    }

    @Override
    public String getName() {
        return "API Summary Doclet";
    }

    @Override
    public Set<? extends Option> getSupportedOptions() {
        Option headingOption = new Option() {
            @Override
            public int getArgumentCount() {
                return 1;
            }

            @Override
            public String getDescription() {
                return "Heading printed before the API summary";
            }

            @Override
            public Kind getKind() {
                return Kind.OTHER;
            }

            @Override
            public List<String> getNames() {
                return List.of("--api-heading");
            }

            @Override
            public String getParameters() {
                return "<text>";
            }

            @Override
            public boolean process(String option, List<String> arguments) {
                heading = arguments.get(0);
                return true;
            }
        };

        return Set.of(headingOption);
    }

    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean run(DocletEnvironment environment) {
        PrintWriter out = reporter.getStandardWriter();
        out.println(heading);

        for (TypeElement type :
                ElementFilter.typesIn(environment.getIncludedElements())) {
            out.println(type.getQualifiedName());

            String comment =
                    environment.getElementUtils().getDocComment(type);
            if (comment != null) {
                out.println("  " + comment.replace('\n', ' ').trim());
            }

            for (ExecutableElement method :
                    ElementFilter.methodsIn(type.getEnclosedElements())) {
                Set<Modifier> modifiers = method.getModifiers();
                boolean visible =
                        modifiers.contains(Modifier.PUBLIC)
                        || modifiers.contains(Modifier.PROTECTED);

                if (visible) {
                    String parameters = method.getParameters().stream()
                            .map(parameter -> parameter.asType().toString())
                            .collect(Collectors.joining(", "));

                    out.println(
                            "  " + method.getReturnType() + " "
                            + method.getSimpleName()
                            + "(" + parameters + ")"
                    );
                }
            }
        }

        out.flush();
        return true;
    }
}
~~~

Tệp \`src/com/acme/api/Greeting.java\`:

~~~java
package com.acme.api;

/** A small greeting service. */
public class Greeting {

    /** Returns a greeting for the given name. */
    public String greet(String name) {
        return "Hello, " + name + "!";
    }

    private void internalCheck() {
    }
}
~~~

### Bước 1: Biên dịch custom doclet

Từ thư mục gốc \`custom-doclet-demo\`:

~~~bash
mkdir -p build/doclet
javac -d build/doclet src/doclet/ApiSummaryDoclet.java
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/doclet | Out-Null
javac -d build/doclet src/doclet/ApiSummaryDoclet.java
~~~

Doclet class được tạo tại \`build/doclet/doclet/ApiSummaryDoclet.class\`. Đây là class mà Javadoc sẽ nạp bằng \`-docletpath\`.

### Bước 2: Chạy Javadoc với custom doclet

Linux/macOS:

~~~bash
javadoc -quiet \
  -doclet doclet.ApiSummaryDoclet \
  -docletpath build/doclet \
  --api-heading "Customer API" \
  --source-path src \
  -subpackages com.acme.api
~~~

Windows PowerShell:

~~~powershell
javadoc -quiet -doclet doclet.ApiSummaryDoclet -docletpath build/doclet --api-heading "Customer API" --source-path src -subpackages com.acme.api
~~~

Javadoc tìm source trong \`src\`, chọn package \`com.acme.api\`, nạp \`ApiSummaryDoclet\` từ \`build/doclet\` và truyền giá trị \`Customer API\` cho option \`--api-heading\`.

### Bước 3: Kiểm tra output

Với JDK 24.0.2, output của ví dụ là:

~~~text
Customer API
com.acme.api.Greeting
  A small greeting service.
  java.lang.String greet(java.lang.String)
~~~

Method \`internalCheck()\` không xuất hiện vì doclet chỉ in method có modifier public hoặc protected. \`getDocComment(type)\` lấy phần mô tả class từ Javadoc comment. \`getReturnType()\` và \`getParameters()\` cung cấp kiểu trả về và kiểu tham số của method.

Ví dụ tạo báo cáo văn bản qua \`Reporter.getStandardWriter()\`. Nó không tạo bộ trang HTML như Standard Doclet. Nếu muốn sinh HTML/JSON thành file, doclet cần định nghĩa cách chọn thư mục output và tự ghi các file tương ứng.

## 8. Duyệt phần tử và tránh bỏ sót API

Khi xây dựng doclet thực tế, cần quyết định chính xác loại phần tử cần xử lý.

### Phần tử được chỉ định và phần tử được đưa vào tài liệu

\`getSpecifiedElements()\` hữu ích khi cần biết người dùng chỉ định package hoặc source nào trên command line. \`getIncludedElements()\` hữu ích khi cần xử lý các type/module đã được Javadoc chọn để đưa vào tài liệu.

Không nên mặc định mọi type trên source path đều được chọn. Các tùy chọn visibility, package, module và source selection ảnh hưởng tập phần tử được đưa vào.

### Thành viên khai báo trực tiếp và thành viên kế thừa

Trong ví dụ, \`type.getEnclosedElements()\` chỉ trả về thành viên khai báo trực tiếp trong type. Nếu cần liệt kê cả method kế thừa, dùng:

~~~java
environment.getElementUtils().getAllMembers(type)
~~~

Sau đó lọc các phần tử bằng \`ElementFilter.methodsIn(...)\` và xử lý modifier, override/hide theo yêu cầu của báo cáo.

Nếu mục tiêu là xuất API công khai, cần quyết định có bao gồm method kế thừa, bridge method, synthetic member, constructor, record component và nested type hay không. Đừng coi danh sách thành viên khai báo trực tiếp là toàn bộ API mà client có thể nhìn thấy.

### Type và generic

\`ExecutableElement.getReturnType()\` và \`getParameters()\` cung cấp kiểu dưới dạng \`TypeMirror\`. \`TypeMirror.toString()\` hữu ích cho báo cáo đơn giản, nhưng không phải định dạng serialization ổn định cho mọi mục đích.

Nếu cần xử lý generic, subtype hoặc erasure, hãy dùng \`Types\` thay vì phân tích chuỗi. Nếu cần tên type chuẩn, dùng \`Elements.getBinaryName()\` hoặc \`getQualifiedName()\` tùy mục đích. Tên nhị phân và tên đầy đủ khác nhau với nested class.

## 9. Đọc và kiểm tra Javadoc tags

Một custom doclet thường cần xác minh tài liệu có đầy đủ hay không. Có thể đọc phần comment dạng văn bản:

~~~java
String comment = environment.getElementUtils().getDocComment(element);
~~~

Cách này thuận tiện khi chỉ cần phần mô tả đơn giản. Khi cần phân biệt tag, dùng \`DocTrees\`:

~~~java
DocTrees docTrees = environment.getDocTrees();
DocCommentTree tree = docTrees.getDocCommentTree(element);
~~~

Sau đó có thể kiểm tra:

- Method có \`@param\` cho các tham số hay không.
- Method trả về giá trị có \`@return\` hay không.
- Method khai báo checked exception có \`@throws\` tương ứng hay không.
- Deprecated API có \`@deprecated\` explanation hay không.
- Class có mô tả, ví dụ và liên kết tham chiếu cần thiết hay không.

Không nên dùng regex đơn giản trên comment thô để phân tích mọi tag. Cú pháp Javadoc có inline tags, HTML, link và cấu trúc lồng nhau; DocTree API giữ lại cấu trúc để xử lý đúng hơn.

Có thể báo cảnh báo tại phần tử có vấn đề:

~~~java
reporter.print(
    Diagnostic.Kind.WARNING,
    element,
    "Missing @param documentation."
);
~~~

Một doclet kiểm tra chất lượng có thể tích lũy số lỗi/cảnh báo, in vị trí phần tử và trả \`false\` nếu chính sách yêu cầu build thất bại khi phát hiện lỗi.

## 10. Tạo file đầu ra tùy chỉnh

Custom doclet có thể tạo đầu ra ngoài console, ví dụ Markdown hoặc JSON. Có hai quyết định cần thiết:

1. Xác định đường dẫn đầu ra bằng option riêng, ví dụ \`--output-dir <path>\`.
2. Tạo thư mục và ghi file với encoding rõ ràng, thường là UTF-8.

Ví dụ phần ghi file bằng Java NIO:

~~~java
Path output = Path.of(outputDirectory, "api-summary.md");
Files.createDirectories(output.getParent());
Files.writeString(output, markdown, StandardCharsets.UTF_8);
~~~

Trong code thật, cần xử lý \`IOException\`, kiểm tra đường dẫn và báo lỗi qua \`Reporter\`. Không nên giả định \`-d\` của Standard Doclet tự động có hiệu lực với custom doclet. Nếu doclet không hỗ trợ option đó, hãy khai báo option output riêng hoặc chủ động tích hợp file manager phù hợp.

Nếu tạo HTML, cần escape ký tự từ source/comment trước khi đưa vào HTML. Không chèn trực tiếp nội dung Javadoc hoặc tên phần tử vào HTML mà không xử lý ký tự đặc biệt. Nếu tạo JSON, dùng JSON serializer phù hợp thay vì ghép chuỗi thủ công.

Đối với tài liệu lớn, nên tạo các model dữ liệu trung gian rồi mới render Markdown/HTML/JSON. Cách này tách phần phân tích Java model khỏi phần trình bày và giúp kiểm thử output dễ hơn.

## 11. Custom doclet, Standard Doclet và Taglet

Ba lựa chọn này giải quyết những nhu cầu khác nhau:

| Công cụ | Khi nào dùng |
|---|---|
| Standard Doclet | Cần bộ tài liệu HTML chuẩn của Javadoc, navigation và liên kết API. |
| Custom Doclet | Cần thay đổi cách duyệt mô hình và tạo đầu ra theo định dạng riêng. |
| Taglet | Cần xử lý một custom Javadoc tag hoặc mở rộng cách hiển thị tag trong tài liệu chuẩn. |

Ví dụ, nếu muốn tag \`@apiNote\` được xử lý theo một cách riêng nhưng vẫn giữ toàn bộ HTML chuẩn, Taglet thường là điểm mở rộng nhỏ hơn. Nếu muốn xuất toàn bộ API thành một schema JSON độc lập, custom doclet phù hợp hơn.

Custom doclet không tự động kế thừa các tùy chọn của Standard Doclet. Các option như \`-d\`, \`-windowtitle\`, \`-link\`, \`-stylesheetfile\` và nhiều tùy chọn HTML thuộc Standard Doclet. Khi dùng custom doclet, chỉ dùng những option mà Javadoc tool hoặc doclet hiện tại hỗ trợ.

## 12. Chạy doclet với package, classpath và module

Các tùy chọn đầu vào của Javadoc ảnh hưởng cách source và dependency được phân giải:

| Tùy chọn | Mục đích |
|---|---|
| \`-sourcepath\` hoặc \`--source-path\` | Vị trí tìm source package. |
| \`-classpath\` hoặc \`--class-path\` | Vị trí tìm class/JAR dependency. |
| \`-doclet\` | Tên đầy đủ của custom doclet class. |
| \`-docletpath\` | Vị trí chứa doclet class hoặc JAR. |
| \`-subpackages\` | Chọn package và các package con để xử lý. |
| \`-private\` | Yêu cầu đưa cả thành viên private vào tập tài liệu được chọn. |
| \`--module-path\` | Vị trí tìm application modules. |
| \`--module\` | Chỉ định module cần tạo tài liệu. |

Trên Windows, nhiều đường dẫn trong classpath/module path dùng dấu chấm phẩy để phân tách. Trên Linux/macOS, dùng dấu hai chấm.

Với doclet được đóng gói trong JAR:

~~~bash
javadoc -doclet doclet.ApiSummaryDoclet \
  -docletpath build/api-doclet.jar \
  --source-path src \
  -subpackages com.acme.api
~~~

Nếu doclet hoặc source thuộc module, cần cấu hình module path và module tương ứng. Đảm bảo JDK dùng để chạy Javadoc có module \`jdk.javadoc\`.

## 13. Kiểm thử custom doclet

Custom doclet nên được kiểm thử như một chương trình xử lý source, không chỉ kiểm tra rằng class biên dịch thành công.

Các nhóm kiểm thử hữu ích:

- **Option parsing:** option hợp lệ, thiếu đối số, giá trị rỗng và option không được hỗ trợ.
- **Selection:** public/protected/private, package, nested type và module.
- **Element model:** class, interface, enum, record, annotation, field, constructor và overload.
- **Inheritance:** method khai báo trực tiếp và method kế thừa.
- **Documentation comments:** mô tả, block tags, inline tags, link và HTML.
- **Diagnostics:** warning/error có đúng loại và gắn với đúng phần tử.
- **Output:** encoding UTF-8, escaping, thứ tự ổn định và nội dung đầu ra.
- **Failure handling:** source lỗi, type không resolve được, output path không ghi được.

Nên có fixture source nhỏ với output mong đợi được lưu thành golden file. Khi thay đổi doclet, so sánh output mới với fixture để phát hiện thay đổi ngoài ý muốn.

Có thể chạy Javadoc với \`-verbose\` khi cần xem quá trình xử lý:

~~~bash
javadoc -verbose -doclet doclet.ApiSummaryDoclet \
  -docletpath build/doclet \
  --source-path src \
  -subpackages com.acme.api
~~~

Khi CI cần chặn warning, Javadoc hỗ trợ \`-Werror\` để báo lỗi nếu có warning. Chỉ bật sau khi nhóm đã thống nhất những warning nào cần xử lý và đã kiểm tra output trên JDK mục tiêu.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| \`Cannot find doclet class\` | Sai tên class hoặc \`-docletpath\` không trỏ tới thư mục/JAR chứa doclet. | Kiểm tra package, class name và đường dẫn doclet. |
| \`ClassNotFoundException\` khi khởi chạy | Doclet có dependency không nằm trên đường nạp tương ứng. | Đóng gói dependency hoặc cấu hình classpath/module path cho doclet. |
| \`invalid flag\` cho custom option | Option chưa được trả về từ \`getSupportedOptions()\` hoặc tên option bị trùng. | Kiểm tra \`getNames()\`, \`getArgumentCount()\` và \`process()\`. |
| Doclet không thấy class mong đợi | Package không được chọn, source path sai hoặc visibility filter loại phần tử. | Kiểm tra \`-sourcepath\`, \`-subpackages\`, \`-private\` và \`getIncludedElements()\`. |
| Thiếu method kế thừa | Chỉ duyệt \`getEnclosedElements()\`. | Dùng \`Elements.getAllMembers(type)\` nếu cần API kế thừa. |
| Không đọc được \`@param\` hoặc \`@return\` | Chỉ dùng chuỗi comment hoặc xử lý sai cấu trúc tag. | Dùng \`DocTrees\` và \`DocCommentTree\`. |
| Tài liệu bị trùng member | Vừa duyệt trực tiếp vừa duyệt tất cả thành viên kế thừa mà không loại override/hide. | Xác định quy tắc API cần xuất và dùng \`Elements.overrides()\`/\`hides()\` khi phù hợp. |
| Output HTML bị lỗi ký tự | Nội dung source được đưa thẳng vào HTML mà không escape. | Escape HTML hoặc dùng thư viện render an toàn. |
| Output JSON không hợp lệ | Ghép chuỗi thủ công và không escape dấu nháy, newline hoặc Unicode. | Dùng JSON serializer. |
| Doclet chạy trên JDK mới nhưng cảnh báo source version | \`getSupportedSourceVersion()\` khai báo phiên bản thấp hơn source đang xử lý. | Chọn source version doclet thực sự hỗ trợ và kiểm thử với JDK mục tiêu. |

## 15. Quy trình phát triển custom doclet

Một quy trình thực tế:

1. Xác định đầu ra cần tạo: báo cáo văn bản, Markdown, HTML hay JSON.
2. Xác định loại phần tử cần đọc và quy tắc visibility.
3. Thiết kế option riêng cho output path, package filter hoặc chế độ báo cáo.
4. Triển khai \`Doclet\`, \`Doclet.Option\` và \`run\`.
5. Dùng \`DocletEnvironment\`, \`Elements\`, \`Types\` và \`DocTrees\` để đọc mô hình Java.
6. Dùng \`Reporter\` để phát cảnh báo và lỗi có vị trí.
7. Tạo fixture source bao phủ class, method, generic, inheritance và Javadoc tags.
8. Biên dịch doclet và chạy Javadoc trong test.
9. So sánh output với kết quả mong đợi.
10. Chạy lại trên phiên bản JDK được dự án hỗ trợ và kiểm tra option/diagnostic.

Không nên xây dựng logic phân tích source bằng cách đọc file \`.java\` rồi tìm chuỗi bằng regex nếu mục tiêu là hiểu cấu trúc Java. Javadoc đã cung cấp mô hình phần tử và cây comment; dùng các API này giúp xử lý overload, generic, annotation, nested type và tag chính xác hơn.

## 16. Ghi nhớ

Custom doclet là điểm mở rộng của Javadoc để kiểm soát cách đọc mô hình mã nguồn và tạo đầu ra. \`Doclet\` định nghĩa vòng đời; \`DocletEnvironment\` cung cấp các phần tử được chọn; \`Elements\` và \`Types\` hỗ trợ phân tích khai báo/kiểu; \`DocTrees\` xử lý documentation comments; \`Reporter\` gửi thông báo; \`Doclet.Option\` khai báo tùy chọn riêng.

Khi chỉ cần thêm một loại tag vào HTML chuẩn, cân nhắc Taglet. Khi cần tạo một báo cáo hoặc định dạng tài liệu riêng từ source Java, custom doclet cho phép tổ chức quy trình rõ ràng, có thể kiểm thử và tích hợp vào build.
