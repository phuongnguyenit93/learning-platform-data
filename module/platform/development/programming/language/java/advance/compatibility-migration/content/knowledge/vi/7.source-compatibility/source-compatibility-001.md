# Tên định danh, từ khóa và tên kiểu mới có thể xung đột

Khi nâng phiên bản Java, một dự án có thể không còn biên dịch được dù logic nghiệp vụ không thay đổi. Nguyên nhân đôi khi đến từ những thay đổi nhỏ trong ngôn ngữ: một tên trước đây được phép dùng làm biến hoặc tên kiểu trở thành từ khóa, một từ định danh hạn chế được bổ sung ngữ nghĩa mới, hoặc JDK đưa thêm một kiểu vào package được import tự động hay import bằng dấu sao. Những xung đột này thường xuất hiện ở thời điểm biên dịch và có thể ảnh hưởng đến mã nguồn, thư viện dùng chung, generated source hoặc mã do annotation processor tạo ra.

Bài học này thuộc chủ đề **Java Advance Compatibility Migration**, chương **Tương thích mã nguồn**. Nội dung giải thích các loại xung đột tên khi chuyển Java source level, cách nhận biết lỗi do từ khóa và kiểu mới, cách sửa có kiểm soát, và quy trình kiểm tra để tránh làm thay đổi hành vi của ứng dụng.

## 1. Vì sao một tên hợp lệ ở phiên bản Java cũ có thể trở thành vấn đề?

Ngôn ngữ Java phát triển qua các phiên bản. Mỗi phiên bản có thể bổ sung:

- Từ khóa mới để biểu diễn cấu trúc ngôn ngữ.
- Từ định danh hạn chế hoặc contextual keyword chỉ có ý nghĩa trong một ngữ cảnh.
- Kiểu mới trong các package của JDK.
- Method, constructor hoặc overload mới trong kiểu có sẵn.
- Cú pháp mới làm thay đổi cách parser diễn giải một đoạn mã.

Một identifier từng hợp lệ có thể rơi vào một trong các trường hợp:

1. Trở thành từ khóa và không còn được dùng làm identifier.
2. Trở thành restricted identifier, chỉ bị hạn chế trong một số vị trí cú pháp.
3. Vẫn hợp lệ ở phần lớn vị trí nhưng bị diễn giải khác trong một ngữ cảnh mới.
4. Va chạm với một kiểu mới được JDK cung cấp, khiến tên kiểu đơn giản trở nên mơ hồ.
5. Va chạm với API mới được kế thừa hoặc import, làm một biểu thức trước đây chỉ có một cách hiểu nay có nhiều cách phân giải.

Ví dụ, một codebase cũ có thể chứa:

~~~java
public class Record {
    private String value;
}
~~~

Tên kiểu Record viết hoa vẫn là một identifier Java hợp lệ. Nhưng từ Java 16, JDK bổ sung java.lang.Record làm lớp nền cho record class. Nếu mã nguồn khác dùng wildcard import cho package chứa Record của ứng dụng và đồng thời nhận kiểu từ java.lang, tham chiếu tên đơn giản Record có thể trở nên mơ hồ.

Một trường hợp khác là tên biến:

~~~java
int yield = 10;
~~~

Tên yield có thể xuất hiện như identifier trong một số vị trí, nhưng từ Java 14, yield được dùng trong cú pháp yield statement của switch expression. Nếu mã nguồn dùng tên này trong ngữ cảnh nhạy cảm với cú pháp mới, cần kiểm tra cách compiler phân tích biểu thức.

Vì vậy, khi migration, cần phân biệt một từ trông giống keyword với việc nó thực sự bị cấm ở mọi vị trí. Java có cả keyword thực sự, restricted identifier và contextual keyword.

## 2. Phân biệt keyword, restricted identifier và contextual keyword

### 2.1. Keyword thực sự

Keyword là token dành riêng cho cú pháp Java. Không thể dùng keyword làm tên biến, method, class, interface, package hoặc type parameter.

Ví dụ:

~~~java
int class = 10;       // Không hợp lệ
class return { }      // Không hợp lệ
String package = "";  // Không hợp lệ
~~~

Một số keyword được bổ sung qua các phiên bản lịch sử:

| Từ khóa | Phiên bản Java liên quan | Ý nghĩa |
|---|---:|---|
| assert | Java 1.4 | Kiểm tra điều kiện tại runtime khi assertion được bật |
| enum | Java 5 | Khai báo kiểu liệt kê |
| _ | Java 9 | Một dấu gạch dưới đơn trở thành keyword |
| const, goto | Từ các phiên bản đầu | Từ khóa được dành riêng nhưng không có chức năng Java thông dụng |

Một số từ đã là keyword từ lâu như public, private, static, final, class, interface, extends, implements, return, throw, try và catch.

Điểm đáng chú ý trong migration là identifier chỉ gồm một dấu gạch dưới. Trước Java 9, một số codebase có thể dùng nó làm tên biến hoặc tham số lambda:

~~~java
String _ = readValue();
~~~

Từ Java 9, dấu gạch dưới đơn là keyword và không còn được dùng làm identifier. Nếu cần một tên bỏ qua giá trị, hãy dùng tên có ý nghĩa hoặc một identifier khác:

~~~java
String ignoredValue = readValue();
~~~

Tên bắt đầu bằng dấu gạch dưới nhưng có thêm ký tự, chẳng hạn _value, không phải keyword chỉ vì có dấu gạch dưới đầu tiên.

### 2.2. Restricted identifier

Restricted identifier không phải keyword thông thường ở mọi vị trí. Ngôn ngữ hạn chế cách dùng nó ở một số vị trí cú pháp để dành chỗ cho tính năng mới.

Một số ví dụ quan trọng:

| Restricted identifier | Phiên bản liên quan | Ngữ cảnh cần chú ý |
|---|---:|---|
| var | Java 10 | Dùng làm tên kiểu trong ngữ cảnh khai báo kiểu bị hạn chế; hỗ trợ local variable type inference |
| yield | Java 14 | Dùng trong yield statement của switch expression; một số cách gọi method không định danh có thể bị ảnh hưởng |
| record | Java 16 | Dùng để khai báo record class; bị hạn chế khi dùng làm tên kiểu |
| sealed | Java 17 | Modifier cho sealed class/interface |
| permits | Java 17 | Khai báo các kiểu con được phép của sealed type |

Ví dụ, var không phải keyword tổng quát. Tên biến như sau có thể hợp lệ:

~~~java
int var = 10;
System.out.println(var);
~~~

Nhưng var được dùng làm tên kiểu trong khai báo class hoặc interface có thể không hợp lệ:

~~~java
class var { }  // Không hợp lệ trong source level hỗ trợ var
~~~

Trong khi đó, cú pháp local variable type inference dùng var ở vị trí kiểu:

~~~java
var total = 100;
var names = List.of("An", "Binh");
~~~

Cần phân biệt var trong khai báo biến cục bộ với khai báo field, parameter hoặc kiểu trả về. Java không cho phép dùng var để suy luận kiểu cho mọi loại khai báo.

Tương tự, record được dành cho cú pháp khai báo record:

~~~java
public record CustomerId(String value) { }
~~~

Tên record có chữ thường record mang ý nghĩa cú pháp trong khai báo này. Một identifier viết hoa Record là tên khác vì Java phân biệt chữ hoa và chữ thường.

Với yield, hãy xem ví dụ switch expression:

~~~java
int result = switch (status) {
    case 1 -> 10;
    case 2 -> {
        yield 20;
    }
    default -> 0;
};
~~~

Trong block của switch expression, yield kết thúc nhánh và cung cấp giá trị cho toàn bộ switch expression. Khi một codebase cũ có method hoặc identifier tên yield, compiler mới có thể yêu cầu cách viết rõ ràng hơn ở ngữ cảnh này. Có thể dùng tên method có nghĩa khác, hoặc gọi method qua receiver rõ ràng khi cú pháp cho phép.

### 2.3. Contextual keyword

Contextual keyword chỉ được xem như từ khóa trong một ngữ cảnh cú pháp cụ thể. Ở ngữ cảnh thông thường, từ đó vẫn có thể được dùng làm identifier.

Các nhóm đáng chú ý:

| Contextual keyword hoặc token | Ngữ cảnh sử dụng |
|---|---|
| module, open, opens, requires, transitive, exports, to, uses, provides, with | Module declaration và module directives |
| var | Ngữ cảnh khai báo biến cục bộ có suy luận kiểu |
| yield | Cú pháp yield statement trong switch expression |
| record | Khai báo record |
| sealed, permits, non-sealed | Khai báo sealed class/interface và quan hệ permitted subclasses |
| when | Guard trong pattern matching for switch |

Ví dụ, module có ý nghĩa đặc biệt trong module-info.java:

~~~java
module com.example.orders {
    requires java.sql;
    exports com.example.orders.api;
}
~~~

Nhưng từ module không tự động trở thành keyword trong mọi file Java. Trong một class thông thường, identifier cùng tên vẫn có thể được dùng nếu không nằm trong ngữ cảnh cú pháp dành riêng.

Từ Java 21, when được dùng làm guard trong pattern matching for switch:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text when !text.isBlank() -> "text";
        case String text -> "empty";
        default -> "other";
    };
}
~~~

Từ when trong case label có vai trò cú pháp. Ở một vị trí khai báo biến thông thường, nó không nhất thiết bị cấm.

**Không nên xử lý mọi contextual keyword bằng cách đổi tên hàng loạt.** Hãy xác định vị trí compiler đang hiểu từ đó như cú pháp mới hay như identifier bình thường.

## 3. Các thay đổi Java có thể tạo ra xung đột tên

Khi chuyển source level, cần quan tâm đến thời điểm một tính năng được chuẩn hóa và compiler áp dụng source version nào. Bảng sau là các mốc thường gặp trong quá trình migration.

| Phiên bản | Thay đổi liên quan đến tên | Tác động có thể gặp |
|---|---|---|
| Java 1.4 | assert trở thành keyword | Identifier cũ tên assert không còn hợp lệ |
| Java 5 | enum trở thành keyword | Identifier cũ tên enum không còn hợp lệ |
| Java 9 | _ trở thành keyword; module system bổ sung contextual keywords | Tên đơn _ và cú pháp module cần rà soát |
| Java 10 | var hỗ trợ local variable type inference | Tên var ở vị trí kiểu có thể xung đột |
| Java 14 | yield dùng trong switch expression | Tên yield ở một số ngữ cảnh có thể gây vấn đề |
| Java 16 | record được chuẩn hóa; java.lang.Record xuất hiện | Tên kiểu record và import có thể xung đột |
| Java 17 | sealed, permits và non-sealed được chuẩn hóa | Cú pháp khai báo kiểu con có thể làm identifier bị diễn giải khác |
| Java 21 | when dùng làm guard trong switch pattern | Tên when cần xem xét trong case label |

Đây không phải danh sách mọi thay đổi source compatibility của Java. Nó tập trung vào các tên và cú pháp có thể làm một codebase cũ không biên dịch được hoặc cần sửa cách tham chiếu.

## 4. Xung đột với kiểu mới trong JDK

Ngoài keyword, JDK cũng bổ sung nhiều class và interface. Những kiểu mới có thể trùng tên với kiểu do ứng dụng hoặc thư viện tự định nghĩa.

### 4.1. Vì sao kiểu mới có thể làm tên đơn giản trở nên mơ hồ?

Java tự động import các kiểu public trong package java.lang. Khi một JDK mới bổ sung kiểu vào java.lang, tên kiểu đó có thể xuất hiện trong phạm vi tên của source file mà không cần thêm import.

Ví dụ, Java 16 bổ sung java.lang.Record. Giả sử ứng dụng có một kiểu Record trong package legacy.model và source file dùng wildcard import:

~~~java
import legacy.model.*;

public class ReportService {
    private Record current;
}
~~~

Nếu legacy.model cũng chứa kiểu Record, tham chiếu Record có thể mơ hồ giữa kiểu trong package legacy.model và kiểu java.lang.Record được import tự động theo dạng on-demand. Compiler có thể báo lỗi yêu cầu tham chiếu rõ ràng.

Có thể sửa bằng single-type import:

~~~java
import legacy.model.Record;

public class ReportService {
    private Record current;
}
~~~

Hoặc dùng tên đầy đủ:

~~~java
private legacy.model.Record current;
~~~

Nếu code thực sự muốn dùng java.lang.Record thì tham chiếu rõ ràng kiểu đó. Cần nhớ java.lang.Record là lớp nền cho record class, không phải kiểu dữ liệu thay thế trực tiếp cho mọi class cũ tên Record.

### 4.2. Ví dụ java.lang.Module

Java 9 bổ sung java.lang.Module để biểu diễn module ở runtime. Một thư viện cũ có thể đã có kiểu Module trong package riêng.

~~~java
import legacy.runtime.*;

public class ModuleInspector {
    private Module currentModule;
}
~~~

Nếu legacy.runtime chứa một kiểu Module, tham chiếu đơn giản có thể xung đột với java.lang.Module. Hãy dùng import tường minh hoặc tên đầy đủ để chỉ rõ kiểu mong muốn.

~~~java
import legacy.runtime.Module;

public class ModuleInspector {
    private Module currentModule;
}
~~~

### 4.3. Kiểu mới trong package được wildcard import

Không chỉ java.lang mới có rủi ro. Một JDK mới có thể bổ sung kiểu vào package mà ứng dụng đã import bằng dấu sao.

Java 21 bổ sung các kiểu SequencedCollection, SequencedSet và SequencedMap trong java.util. Giả sử một thư viện cũ cũng định nghĩa kiểu SequencedCollection và source file import wildcard từ cả hai package:

~~~java
import java.util.*;
import legacy.collections.*;

public class CollectionAdapter {
    private SequencedCollection<String> values;
}
~~~

Nếu cả hai package đều cung cấp một kiểu cùng tên, tham chiếu đơn giản có thể mơ hồ. Cách xử lý là import kiểu cụ thể hoặc dùng tên đầy đủ:

~~~java
private java.util.SequencedCollection<String> values;
~~~

Ví dụ này minh họa rủi ro do wildcard import. Nếu dự án chỉ import tường minh một kiểu, hoặc kiểu cùng tên nằm trong package hiện tại, quy tắc phân giải tên có thể khác.

### 4.4. Cùng tên nhưng khác package không phải lúc nào cũng gây lỗi

Java có quy tắc ưu tiên khi phân giải tên kiểu. Một số tình huống:

- Kiểu được khai báo trong cùng compilation unit hoặc cùng package có quy tắc riêng.
- Single-type import có độ ưu tiên khác wildcard import.
- Hai kiểu cùng tên đến từ hai on-demand import có thể gây mơ hồ.
- Kiểu trong java.lang được import tự động theo dạng on-demand.
- Tên đầy đủ luôn giúp chỉ rõ package và kiểu.

Do đó, không thể kết luận cứ có một class mới trùng tên là project sẽ lỗi. Cần xem import và vị trí tham chiếu thực tế.

## 5. Xung đột tên trong source, package và generated code

### 5.1. Identifier ở nhiều vị trí khác nhau

Tên có thể xuất hiện ở nhiều vị trí:

- Tên class, interface, enum hoặc record.
- Tên field và local variable.
- Tên method và constructor.
- Tên parameter.
- Tên generic type parameter.
- Tên package.
- Tên module.
- Tên component trong record.
- Tên pattern variable.
- Tên biến trong lambda.
- Tên được sinh ra bởi annotation processor hoặc code generator.

Một từ có thể hợp lệ ở vị trí này nhưng không hợp lệ ở vị trí khác. Vì vậy, khi compiler báo lỗi, hãy xác định đúng loại identifier và ngữ cảnh.

Ví dụ, var có thể là tên biến:

~~~java
int var = 5;
~~~

Nhưng không thể dùng var như kiểu của field:

~~~java
class Config {
    var value = 5; // Không hợp lệ: var không dùng cho field
}
~~~

Tương tự, tên record có thể được dùng làm tên biến trong một số ngữ cảnh, nhưng không thể dùng như tên kiểu trong cú pháp khai báo bị hạn chế.

### 5.2. Tên kiểu mới và wildcard import

Wildcard import làm code ngắn hơn nhưng khiến phạm vi tên phụ thuộc vào các kiểu public trong package. Khi JDK hoặc dependency bổ sung kiểu mới, một tham chiếu trước đây không mơ hồ có thể trở nên mơ hồ.

Ví dụ:

~~~java
import java.util.*;
import legacy.types.*;

public class Converter {
    private Date value;
}
~~~

Nếu cả java.util và legacy.types đều có kiểu Date, compiler không thể tự chọn kiểu mà source file muốn dùng. Đây là xung đột đã có thể xảy ra trước migration, nhưng việc thêm package hoặc kiểu mới vào một trong các nguồn import có thể làm lỗi xuất hiện sau khi nâng JDK/dependency.

Một cách an toàn hơn là import tường minh:

~~~java
import java.util.Date;
~~~

Nếu cần cả hai kiểu, dùng một import tường minh và một tên đầy đủ tại vị trí còn lại.

### 5.3. Generated source và annotation processor

Một dự án có thể không viết identifier xung đột trực tiếp trong source, nhưng code được sinh ra lại chứa tên đó.

Nguồn generated code thường gồm:

- Annotation processor.
- OpenAPI hoặc Swagger generator.
- JAXB hoặc XML schema generator.
- Query/metamodel generator.
- ORM static metamodel.
- Protobuf hoặc gRPC generator.
- Client SDK generator.
- Công cụ sinh source từ database schema.

Ví dụ, một schema có property tên record. Generator cũ có thể tạo field hoặc method không phù hợp với source level mới. Một generator khác có thể sinh type tên Module, Record hoặc một tên trùng với kiểu vừa được thêm vào JDK.

Khi migration, cần kiểm tra cả:

- Source do con người viết.
- Source được sinh trong build directory.
- Cấu hình generator và version của plugin.
- Template hoặc rule đổi tên.
- Annotation processor chạy với JDK compiler mục tiêu.

Không nên sửa trực tiếp file generated nếu lần build tiếp theo sẽ ghi đè. Hãy sửa schema, template, mapping hoặc nâng generator để đầu ra được tạo đúng.

## 6. Nhận diện lỗi do keyword và type-name collision

Thông báo compiler thường cho biết vị trí và dạng lỗi. Một số nhóm lỗi thường gặp:

| Dạng thông báo | Nguyên nhân có thể |
|---|---|
| identifier expected | Token tại vị trí tên identifier không hợp lệ |
| not a statement | Parser diễn giải token theo cú pháp khác hoặc biểu thức không hợp lệ |
| class, interface, enum, or record expected | Cấu trúc khai báo hoặc vị trí token sai |
| reference to X is ambiguous | Có nhiều kiểu cùng tên trong phạm vi import |
| cannot find symbol | Kiểu hoặc member không được phân giải |
| package X does not exist | Dependency/import không có trong classpath |
| incompatible types | Kiểu được phân giải khác với kiểu mong đợi |
| invalid method declaration | Tên method/constructor hoặc cú pháp khai báo không hợp lệ |

Một lỗi cannot find symbol không tự động có nghĩa identifier đã trở thành keyword. Nó cũng có thể do dependency bị thiếu, import thay đổi, generated source chưa được tạo hoặc profile/configuration không đúng.

Khi migration, hãy phân loại lỗi theo thứ tự:

1. Parser/syntax error.
2. Identifier không hợp lệ hoặc restricted identifier.
3. Ambiguous type reference.
4. Missing import hoặc missing dependency.
5. Type incompatibility.
6. API/member resolution thay đổi.

Phân loại này giúp tránh đổi tên một class khi nguyên nhân thật sự là classpath hoặc import.

## 7. Quy trình điều tra xung đột tên khi nâng Java

### Bước 1 — Xác định source level thực sự

Đừng chỉ xem JDK cài trên máy. Kiểm tra:

- JDK chạy Maven hoặc Gradle.
- Compiler toolchain.
- Source/release target.
- IDE compiler settings.
- CI build parameters.
- Annotation processor và generated source task.

Một dự án có thể dùng JDK mới nhưng vẫn biên dịch theo source release cũ. Nếu compiler chạy với release 8, một số identifier có thể vẫn được chấp nhận theo quy tắc của source level đó. Khi nâng release lên 17 hoặc 21, lỗi mới có thể xuất hiện.

### Bước 2 — Đọc lỗi đầu tiên trong compiler output

Lỗi parser ban đầu thường là nguyên nhân gốc. Những lỗi sau có thể chỉ là hệ quả vì parser đã hiểu sai cấu trúc phần còn lại của file.

Ghi lại:

- File và dòng lỗi.
- Token compiler đang chỉ ra.
- Source release đang dùng.
- JDK compiler thực tế.
- File đó là source thủ công hay generated source.

### Bước 3 — Tìm mọi nơi sử dụng identifier

Tìm theo tên bị báo lỗi trong:

- src/main/java.
- src/test/java.
- Các source set khác.
- Generated source directory.
- Template code generator.
- Schema và file cấu hình sinh code.
- Module descriptor và package declaration.

Có thể dùng ripgrep:

~~~bash
rg -n -w "record|yield|var|sealed|permits|when" src
~~~

Lệnh trên chỉ là tìm kiếm văn bản theo từ. Nó có thể trả về comment, string literal và nơi dùng hợp lệ. Kết quả cần được đọc trong ngữ cảnh Java; không được thay tất cả kết quả theo một phép thay thế toàn cục.

Với tên kiểu mới, tìm theo tên đơn giản và kiểm tra cả import:

~~~bash
rg -n "import .*Record|\\bRecord\\b|import .*Module|\\bModule\\b" src
~~~

Nếu tên đến từ generated source, hãy tìm trong thư mục generated tương ứng của build tool.

### Bước 4 — Kiểm tra import và quy tắc phân giải kiểu

Khi lỗi là ambiguous reference:

- Liệt kê tất cả import có liên quan.
- Kiểm tra package hiện tại.
- Xác định kiểu có được import tự động từ java.lang không.
- Xác định wildcard import nào cung cấp tên trùng.
- Kiểm tra single-type import.
- Dùng fully qualified name để xác nhận kiểu mong muốn.

Ví dụ:

~~~java
import legacy.model.*;
import java.util.*;

class Report {
    Record record;
}
~~~

Nếu legacy.model có kiểu Record, tên Record có thể xung đột với java.lang.Record trên source level tương ứng. Đổi thành:

~~~java
import legacy.model.Record;

class Report {
    Record record;
}
~~~

hoặc:

~~~java
class Report {
    legacy.model.Record record;
}
~~~

### Bước 5 — Xác minh bằng compiler đích

Sau khi sửa một vị trí nhỏ, build lại bằng chính compiler và release đích sẽ dùng trong migration. Đừng chỉ dựa vào IDE, vì IDE có thể dùng JDK hoặc source level khác với CI.

### Bước 6 — Kiểm tra generated code

Nếu lỗi nằm trong generated source, xác định generator và version. Sửa template/schema/configuration hoặc nâng generator. Sau đó xóa và tạo lại generated output theo task chính thức của dự án; không chỉnh trực tiếp kết quả đã sinh rồi coi đó là bản sửa bền vững.

### Bước 7 — Chạy test và kiểm tra API

Đổi tên identifier có thể ảnh hưởng đến:

- Reflection theo tên field/method.
- JSON property hoặc XML element name.
- Serialization.
- ORM mapping.
- Spring bean name hoặc property binding.
- Expression language.
- Public API và consumer.
- Native image reflection configuration.
- Code generator và client SDK.

Một thay đổi tên có thể làm compile thành công nhưng thay đổi contract bên ngoài. Cần xác nhận những nơi dùng tên theo chuỗi hoặc theo convention.

## 8. Cách sửa theo từng loại xung đột

### 8.1. Identifier trở thành keyword

Nếu tên cũ thực sự trở thành keyword, đổi tên identifier thành tên thể hiện ý nghĩa.

Ví dụ:

~~~java
// Trước đây: hợp lệ với source level trước Java 9
String _ = readValue();

// Sau khi nâng source level
String ignoredValue = readValue();
~~~

Không nên thay bằng một tên chung như value nếu ngữ nghĩa có thể rõ hơn. Nếu identifier là một phần public API, cần đánh giá tương thích source và binary của consumer.

### 8.2. Restricted identifier chỉ xung đột ở một vị trí

Nếu identifier vẫn hợp lệ ở vị trí hiện tại, có thể không cần đổi tên. Tuy nhiên, nếu cú pháp mới khiến code khó đọc hoặc parser không phân giải như mong muốn, đổi tên thường làm code rõ hơn.

Ví dụ:

~~~java
int yield = 5;
int result = yield + 10;
~~~

Có thể giữ nguyên nếu source context hợp lệ. Nhưng nếu code có method hoặc biểu thức dễ bị nhầm với yield statement, nên đổi tên thành resultValue hoặc computedValue, hoặc làm rõ receiver/cách gọi.

### 8.3. Hai kiểu có cùng simple name

Dùng single-type import hoặc fully qualified name:

~~~java
import legacy.model.Record;

class Exporter {
    private Record model;
    private java.lang.Record baseRecord;
}
~~~

Lưu ý java.lang.Record là lớp nền trừu tượng cho record class. Nó không đại diện cho kiểu legacy.model.Record.

### 8.4. Wildcard import gây mơ hồ

Thay wildcard import bằng import cụ thể cho các kiểu được sử dụng:

~~~java
import java.util.List;
import java.util.Map;
import legacy.collections.CustomSequence;
~~~

Không nhất thiết phải loại bỏ mọi wildcard import trong toàn bộ dự án. Chỉ cần xử lý những file có tên kiểu mơ hồ hoặc có rủi ro thay đổi khi nâng JDK/dependency.

### 8.5. Generated code có tên xung đột

Ưu tiên xử lý tại nguồn sinh:

- Cập nhật generator lên phiên bản hỗ trợ source level mục tiêu.
- Cấu hình reserved words hoặc name mapping nếu generator cung cấp.
- Đổi tên property/schema theo quy tắc tương thích.
- Cập nhật template sinh code.
- Đảm bảo generated source được tạo lại ổn định.

Nếu tên trong schema là contract công khai, đổi tên trực tiếp có thể làm thay đổi JSON field, endpoint, database column hoặc tên method mà consumer đang sử dụng. Cần dùng mapping để giữ contract khi cần.

## 9. Bảo toàn contract khi đổi tên

Đổi tên identifier trong source không phải lúc nào cũng chỉ là refactor nội bộ.

### 9.1. Public Java API

Nếu class hoặc method là public/protected trong thư viện được consumer biên dịch riêng, đổi tên có thể làm source hoặc binary compatibility bị phá vỡ.

Ví dụ, thư viện có:

~~~java
public class LegacyOptions {
    public String record;
}
~~~

Nếu đổi field thành recordName, consumer đang truy cập options.record sẽ không còn biên dịch hoặc có thể lỗi liên kết tùy cách thay đổi API.

Có thể giữ API cũ bằng method tương thích hoặc adapter trong một giai đoạn, nếu chính sách API cho phép. Cần xác định rõ deprecation period và phiên bản loại bỏ.

### 9.2. JSON và serialization

Field name có thể trở thành JSON property name theo convention:

~~~java
public class Event {
    private String record;
}
~~~

Đổi thành recordName có thể làm JSON output thay đổi từ:

~~~json
{"record":"created"}
~~~

thành:

~~~json
{"recordName":"created"}
~~~

Nếu client cũ cần tiếp tục hoạt động, có thể dùng annotation mapping để giữ property name cũ trong khi đổi tên field Java, tùy thư viện serialization.

Ví dụ với Jackson:

~~~java
public class Event {
    @JsonProperty("record")
    private String recordName;
}
~~~

Cần kiểm tra cả serialize và deserialize, getter/setter, constructor binding và schema công bố.

### 9.3. ORM và database mapping

Tên field có thể ảnh hưởng tới naming strategy hoặc mapping mặc định. Nếu đổi field, xác nhận:

- Tên cột được ánh xạ có thay đổi không.
- Query JPQL/HQL có tham chiếu property cũ không.
- Criteria API hoặc metamodel generated có bị ảnh hưởng không.
- Migration database có cần thiết không.

Dùng annotation mapping tường minh nếu muốn tên Java thay đổi nhưng tên database giữ nguyên.

### 9.4. Reflection, framework scanning và cấu hình theo tên

Một số framework hoặc hệ thống plugin truy cập class/method/field theo chuỗi. Tìm kiếm tĩnh có thể bỏ sót tên được tạo từ property hoặc cấu hình runtime. Cần kiểm tra:

- Annotation.
- XML configuration.
- application properties/yaml.
- Expression language.
- ServiceLoader.
- Reflection utilities.
- Native image reflection metadata.
- External integration contract.

Đổi tên an toàn phải xét đến các đường tham chiếu theo tên, không chỉ các tham chiếu được compiler kiểm tra.

## 10. Kiểm tra source compatibility theo nhiều Java release

Một dự án thư viện có thể cần hỗ trợ nhiều release. Khi đó, nên compile và test theo từng release được cam kết.

Ví dụ, dùng JDK 21 để build nhưng giữ release 17:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Trong Maven:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Trong Gradle:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Cấu hình release giới hạn cú pháp và API nền tảng tương ứng, nhưng không tự động bảo đảm dependency bên thứ ba có cùng baseline. Cần xác nhận dependency graph và runtime thực tế.

Nếu ứng dụng hỗ trợ Java 17 và Java 21, nên có test matrix chạy trên cả hai runtime khi có thể. Một số lỗi chỉ xuất hiện ở runtime mới do thay đổi hành vi hoặc API; một số lỗi khác xuất hiện ở runtime cũ do dependency đã được build bằng release quá mới.

## 11. Ví dụ tổng hợp: nâng source level từ Java 8 lên Java 21

Giả sử codebase cũ có các trường hợp sau trong hai source file riêng:

~~~java
// Record.java
public class Record {
    private String value;
}
~~~

~~~java
// LegacyParser.java
public class LegacyParser {
    public String parse(String _) {
        return _;
    }
}
~~~

Khi nâng source level, có thể gặp các nhóm vấn đề:

- Dấu gạch dưới đơn không còn được phép dùng làm identifier từ Java 9. Đây là một ví dụ thực tế về identifier từng hợp lệ ở source level cũ nhưng trở thành keyword.
- Kiểu Record viết hoa vẫn là tên identifier, nhưng có thể xung đột với java.lang.Record khi được import qua wildcard.
- Generated code hoặc annotation processor có thể sinh ra identifier trùng với restricted identifier mới.

Một phiên bản sửa rõ nghĩa hơn:

~~~java
// LegacyRecord.java
package com.example.legacy;

public class LegacyRecord {
    private String value;
}
~~~

~~~java
// LegacyParser.java
package com.example.legacy;

public class LegacyParser {
    public String parse(String input) {
        return input;
    }
}
~~~

Nếu cần giữ public class Record do contract hiện có, không nhất thiết phải đổi class đó ngay. Có thể dùng import tường minh hoặc fully qualified name ở những nơi có ambiguity, sau đó lập kế hoạch thay đổi API riêng nếu thực sự cần.

Ví dụ trên có mục đích minh họa nhóm lỗi; khi xử lý codebase thực tế, hãy dựa vào compiler output và vị trí source cụ thể.

## 12. Quy trình migration cho identifier và type-name collision

Một quy trình có thể áp dụng cho từng module:

1. Ghi nhận JDK compiler, source/release target và module đang build.
2. Chạy compile trên source level mục tiêu để thu thập lỗi thực tế.
3. Phân loại lỗi: keyword, restricted identifier, contextual keyword, ambiguous type, missing import hoặc generated code.
4. Tìm các vị trí khai báo và tham chiếu identifier bị ảnh hưởng.
5. Kiểm tra import, package và kiểu mới trong JDK.
6. Kiểm tra source generator và annotation processor.
7. Chọn cách sửa nhỏ nhất: rename, import tường minh, fully qualified name hoặc sửa generator.
8. Đánh giá public API, JSON/XML, database mapping và reflection.
9. Biên dịch lại bằng compiler mục tiêu.
10. Chạy unit, integration và contract tests.
11. Lưu các thay đổi source compatibility và lý do trong migration record.

Không nên đổi tên hàng loạt bằng search-and-replace nếu chưa phân biệt identifier, string literal, comment, JSON property, SQL column và tên method được gọi bằng reflection.

## 13. Công cụ hỗ trợ tìm kiếm và xác minh

### 13.1. Ripgrep

Có thể tìm nhanh những từ thường liên quan đến cú pháp mới:

~~~bash
rg -n -w "assert|enum|var|yield|record|sealed|permits|when" src
~~~

Tìm tên kiểu có thể va chạm:

~~~bash
rg -n "Record|Module|SequencedCollection|SequencedMap|SequencedSet" src
~~~

Kết quả cần được phân loại thủ công. Ripgrep tìm văn bản, không hiểu đầy đủ ngữ nghĩa Java.

### 13.2. Compiler của JDK đích

Compiler là bằng chứng quan trọng nhất về việc source có biên dịch theo release đã chọn hay không.

~~~bash
javac --release 21 -d out src/com/example/Main.java
~~~

Trong dự án Maven hoặc Gradle, hãy chạy task compile thực tế để bảo đảm plugin, annotation processor và source set đều được xử lý.

### 13.3. IDE inspections và static analysis

IDE có thể cảnh báo:

- Identifier bị hạn chế trong source level mới.
- Import không rõ ràng.
- Type reference mơ hồ.
- API deprecated hoặc không còn khả dụng.
- Cấu hình compiler khác với JDK dự kiến.

Static analysis có thể phát hiện thêm một số pattern, nhưng phải dùng đúng source level và JDK target. IDE không thay thế CI build.

### 13.4. Generated source inspection

Nếu build sinh source, hãy tìm output trong các thư mục như:

~~~text
target/generated-sources/
target/generated-test-sources/
build/generated/
build/generated/sources/
~~~

Tên thư mục thực tế phụ thuộc plugin. Kiểm tra task hoặc plugin sinh file để biết output nào thuộc generator nào.

Không sửa generated file như một bản sửa lâu dài. Hãy cập nhật nguồn sinh và chạy lại generator.

## 14. Ghi nhận kết quả sửa xung đột

Một bản ghi migration nên thể hiện:

~~~text
MODULE
  Module:
  Source release before:
  Source release target:
  Compiler JDK:
  Build tool:

COLLISION
  Identifier/type:
  Source location:
  Collision category:
  New Java feature or JDK type:
  Compiler diagnostic:

RESOLUTION
  Rename / explicit import / qualified name / generator update:
  Files changed:
  Public API impact:
  Serialization/database/reflection impact:

VALIDATION
  Compile command:
  Compile result:
  Unit test result:
  Integration/contract test result:
  Generated source check:

FOLLOW-UP
  Consumer compatibility:
  Deprecation or migration note:
  Remaining risk:
~~~

Ghi lại cả những vị trí không cần sửa nhưng đã được xác minh. Điều này giúp người review hiểu phạm vi kiểm tra và tránh lặp lại điều tra ở lần migration sau.

## 15. Ghi nhớ

Khi nâng Java source level, hãy xem tên định danh theo đúng ngữ cảnh:

- **Keyword:** không được dùng làm identifier.
- **Restricted identifier:** chỉ bị hạn chế ở một số vị trí cú pháp.
- **Contextual keyword:** có ý nghĩa đặc biệt trong một ngữ cảnh nhất định.
- **Tên kiểu mới:** có thể xung đột với kiểu cũ thông qua import, đặc biệt là wildcard import và kiểu java.lang được import tự động.
- **Generated identifier:** cần xử lý tại schema, template hoặc generator thay vì sửa output thủ công.

Khi compiler báo lỗi, hãy xác định source level, đọc lỗi đầu tiên, kiểm tra import và package, tìm cả source thủ công lẫn generated source, rồi chọn cách sửa giữ được contract của ứng dụng.

Migration hoàn tất khi code biên dịch bằng compiler và release đích, các kiểu được phân giải đúng, generated code tái tạo ổn định và những contract bên ngoài vẫn được kiểm chứng.
