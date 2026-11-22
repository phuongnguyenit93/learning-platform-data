# Phân tích cảnh báo compiler với `-Xlint` và chính sách xử lý cảnh báo

Khi nâng cấp JDK, compiler có thể bắt đầu hiển thị những cảnh báo mà trước đây nhóm phát triển chưa nhìn thấy. Một số cảnh báo xuất hiện vì compiler mới nhận diện thêm vấn đề; một số khác đến từ API đã deprecated, kiểu generic không an toàn, phép chuyển kiểu dư thừa hoặc cấu hình build thay đổi. Nếu bỏ qua toàn bộ cảnh báo, nhóm có thể bỏ lỡ những dấu hiệu sớm về lỗi tương thích và nợ kỹ thuật. Nếu biến mọi cảnh báo thành lỗi ngay lập tức, quá trình nâng cấp lại có thể bị chặn bởi một lượng lớn cảnh báo cũ hoặc cảnh báo từ mã được sinh tự động.

`javac -Xlint` cung cấp các nhóm cảnh báo chi tiết hơn để nhóm chủ động quan sát những vấn đề mà compiler có thể phát hiện. Một chính sách cảnh báo tốt cần xác định cảnh báo nào phải được sửa, cảnh báo nào được chấp nhận tạm thời, cách ghi nhận ngoại lệ và thời điểm áp dụng `-Werror` để ngăn cảnh báo mới lọt vào codebase.

## 1. Cảnh báo compiler là gì?

Compiler Java kiểm tra mã nguồn và tạo bytecode. Trong quá trình đó, compiler có thể phát hiện những cấu trúc hợp lệ về mặt cú pháp và kiểu nhưng có khả năng gây lỗi, khó bảo trì hoặc phụ thuộc vào hành vi không an toàn.

Ví dụ, mã nguồn sau vẫn có thể biên dịch:

```java
import java.util.List;

public class Example {
    @SuppressWarnings("unused")
    public void printFirst(List values) {
        String first = (String) values.get(0);
        System.out.println(first);
    }
}
```

Phương thức dùng raw type `List` và ép kiểu thủ công. Compiler không biết phần tử trong danh sách có thật sự là `String` hay không. Nếu danh sách chứa một kiểu khác, chương trình có thể ném `ClassCastException` khi chạy. Với các tùy chọn lint phù hợp, compiler có thể cảnh báo về raw type hoặc phép ép kiểu không được kiểm tra.

Thông thường, cảnh báo không làm compiler dừng build. Compiler vẫn tạo class file, nhưng phát ra thông tin để lập trình viên đánh giá. Điều này khác với lỗi compile, vốn khiến quá trình biên dịch thất bại.

| Loại thông báo | Ý nghĩa | Kết quả thường thấy |
|---|---|---|
| Error | Mã nguồn hoặc cấu hình không đáp ứng quy tắc biên dịch | Compiler không tạo đầu ra thành công cho phần bị lỗi. |
| Warning | Compiler phát hiện một cấu trúc đáng chú ý hoặc có rủi ro | Build vẫn có thể thành công nếu không bật chính sách coi warning là error. |
| Note | Thông tin bổ sung, thường liên quan đến API deprecated hoặc thao tác compiler | Cần đọc nội dung để hiểu ngữ cảnh; không phải lúc nào cũng là warning có thể bật/tắt bằng cùng một lint key. |

Không phải mọi vấn đề chất lượng đều được compiler phát hiện. `-Xlint` không thay thế static analysis, kiểm thử, review hoặc quan sát runtime. Nó chỉ mở rộng các chẩn đoán mà `javac` có thể đưa ra trong phạm vi mã nguồn và cấu hình biên dịch.

## 2. `-Xlint` hoạt động như thế nào?

`-Xlint` là tùy chọn của `javac` để bật các cảnh báo bổ sung. Có thể bật toàn bộ nhóm cảnh báo hoặc chọn từng nhóm theo tên.

### 2.1. Bật các nhóm cảnh báo

Một số cách sử dụng phổ biến:

```bash
# Bật các cảnh báo được javac khuyến nghị
javac -Xlint Example.java

# Bật tất cả các nhóm cảnh báo mà compiler hỗ trợ
javac -Xlint:all Example.java

# Chỉ bật một số nhóm cụ thể
javac -Xlint:deprecation,unchecked,rawtypes Example.java

# Bật tất cả rồi loại trừ một nhóm
javac -Xlint:all,-serial Example.java
```

`-Xlint` bật các cảnh báo được compiler khuyến nghị. `-Xlint:all` yêu cầu bật tất cả các nhóm cảnh báo mà phiên bản compiler hỗ trợ. Danh sách và phạm vi của các lint key có thể thay đổi theo JDK, vì vậy hãy kiểm tra compiler đang dùng thay vì dựa vào một danh sách cố định trên Internet.

Có thể xem các nhóm được hỗ trợ bằng:

```bash
javac --help-lint
```

Lệnh này hiển thị các lint key và mô tả tương ứng trong chính phiên bản `javac` đang chạy. Khi nâng JDK, đây là cách trực tiếp để biết compiler mới có thêm hoặc thay đổi nhóm cảnh báo nào.

### 2.2. Bật và tắt từng nhóm

Cú pháp tổng quát:

```text
-Xlint:<key>
-Xlint:-<key>
```

Ví dụ:

```bash
javac -Xlint:deprecation -Xlint:unchecked Example.java
javac -Xlint:all,-deprecation Example.java
```

Tùy chọn thứ hai bật tất cả nhóm rồi tắt riêng nhóm `deprecation`. Có thể kết hợp nhiều key trong cùng một tùy chọn bằng dấu phẩy. Nên ghi rõ chính sách trong build script để mọi lập trình viên và CI sử dụng cùng cấu hình.

Không nên tắt cảnh báo chỉ để làm output sạch. Trước khi loại trừ một nhóm, hãy xác định vì sao nhóm đó không phù hợp với project, phần mã nào bị ảnh hưởng và cách theo dõi rủi ro còn lại.

### 2.3. Hiểu cấu trúc một dòng cảnh báo

Một cảnh báo có thể có dạng:

```text
Example.java:12: warning: [unchecked] unchecked conversion
    List<String> names = rawNames;
                        ^
  required: List<String>
  found:    List
```

Các thành phần cần đọc:

- `Example.java:12`: file và dòng phát sinh cảnh báo.
- `warning`: đây là cảnh báo, chưa phải lỗi compile.
- `[unchecked]`: lint key để nhận biết nhóm cảnh báo.
- `unchecked conversion`: mô tả ngắn vấn đề compiler phát hiện.
- `required` và `found`: kiểu mà code mong đợi và kiểu thực tế compiler nhìn thấy.

Lint key trong ngoặc vuông giúp nhóm tìm đúng tài liệu và chọn chính sách xử lý. Khi báo cáo CI, nên giữ lại cả file, dòng, key và thông điệp thay vì chỉ đếm tổng số warning.

## 3. Những nhóm cảnh báo thường gặp

Tên lint key và chi tiết cảnh báo có thể khác nhau theo phiên bản JDK. Luôn xác nhận bằng `javac --help-lint` của compiler đang dùng. Các nhóm dưới đây là những ví dụ phổ biến và hữu ích khi nâng cấp dự án Java.

### 3.1. `deprecation`: sử dụng API đã deprecated

Một API được đánh dấu `@Deprecated` khi nhà cung cấp muốn thông báo rằng API đó không còn được khuyến nghị sử dụng. API có thể vẫn hoạt động, nhưng có thể đã có lựa chọn thay thế tốt hơn hoặc có kế hoạch loại bỏ.

Ví dụ:

```java
class LegacyClock {
    @Deprecated
    public long currentTime() {
        return System.currentTimeMillis();
    }
}

class ReportService {
    long createdAt() {
        return new LegacyClock().currentTime();
    }
}
```

Khi bật `-Xlint:deprecation`, compiler có thể cảnh báo lời gọi `currentTime()` đã deprecated.

```bash
javac -Xlint:deprecation ReportService.java
```

Khi gặp cảnh báo này, cần tìm API thay thế và đọc tài liệu của API cũ lẫn API mới. Đừng thay thế theo tên gọi một cách máy móc: API mới có thể khác về đơn vị thời gian, timezone, xử lý null, ngoại lệ hoặc cách làm tròn.

### 3.2. `removal`: API được đánh dấu dự kiến loại bỏ

Một số API deprecated còn được đánh dấu `forRemoval = true`:

```java
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
    // Implementation cũ
}
```

Đây là tín hiệu mạnh hơn việc deprecated thông thường: API được dự kiến loại bỏ trong một phiên bản tương lai. Với compiler hỗ trợ lint key `removal`, có thể bật riêng:

```bash
javac -Xlint:removal Example.java
```

Khi nâng cấp JDK, cần phân biệt cảnh báo deprecated nói chung với cảnh báo removal. API chưa bị loại bỏ ở JDK hiện tại vẫn có thể làm ứng dụng lỗi ở JDK mục tiêu sau này. Nên ưu tiên lập kế hoạch thay thế cho các API có `forRemoval = true`.

### 3.3. `unchecked`: thao tác generic không được kiểm tra đầy đủ

Java dùng type erasure cho generic. Một số phép chuyển kiểu hoặc lời gọi qua raw type không thể được compiler xác minh đầy đủ khi chạy. Cảnh báo unchecked cho biết chương trình đang dựa vào một giả định kiểu mà compiler không thể chứng minh.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

class GenericExample {
    @SuppressWarnings("unchecked")
    List<String> names(List rawValues) {
        return (List<String>) rawValues;
    }
}
```

Phép ép kiểu này không kiểm tra từng phần tử trong danh sách. Nếu danh sách chứa một số nguyên, lỗi có thể chỉ xuất hiện khi phần tử được đọc và ép về `String`.

Cách sửa tốt hơn là khai báo generic từ đầu:

```java
import java.util.List;

class GenericExample {
    List<String> names(List<String> values) {
        return values;
    }
}
```

Nếu dữ liệu đi vào từ một API không có generic, cần kiểm tra kiểu ở ranh giới nhận dữ liệu và chuyển đổi một cách có kiểm soát. Không nên dùng `@SuppressWarnings("unchecked")` để che một giả định kiểu chưa được chứng minh.

### 3.4. `rawtypes`: sử dụng raw type

Raw type là cách dùng một kiểu generic mà bỏ qua tham số kiểu:

```java
List values = new ArrayList();
values.add("Java");
values.add(21);
```

Compiler không thể bảo đảm danh sách chỉ chứa một kiểu phần tử. Nên khai báo rõ:

```java
List<String> values = new ArrayList<>();
values.add("Java");
```

Raw type đôi khi xuất hiện ở API cũ hoặc ranh giới tương tác với thư viện legacy. Khi đó, nên cô lập phần tương tác và chuyển đổi sang kiểu an toàn ngay tại ranh giới thay vì để raw type lan ra toàn bộ ứng dụng.

### 3.5. `serial`: lớp Serializable thiếu thông tin phiên bản

Một lớp triển khai `Serializable` thường nên khai báo `serialVersionUID` rõ ràng:

```java
import java.io.Serializable;

public class CustomerRecord implements Serializable {
    private String id;
    private String name;
}
```

Nếu không khai báo, JVM có thể tính serialVersionUID mặc định dựa trên cấu trúc lớp. Những thay đổi trong class có thể làm giá trị được tính thay đổi, khiến dữ liệu serialize từ phiên bản trước không còn đọc được như mong đợi.

Có thể khai báo:

```java
import java.io.Serializable;

public class CustomerRecord implements Serializable {
    private static final long serialVersionUID = 1L;

    private String id;
    private String name;
}
```

`serialVersionUID` giúp kiểm soát việc nhận diện phiên bản serialized form, nhưng không tự động bảo đảm mọi thay đổi field đều tương thích dữ liệu. Cần đọc serialization specification và kiểm thử dữ liệu thực tế khi ứng dụng lưu object lâu dài hoặc trao đổi serialized object giữa các phiên bản.

### 3.6. `cast`: phép ép kiểu dư thừa hoặc không cần thiết

Compiler có thể cảnh báo phép ép kiểu không cần thiết:

```java
String name = (String) "Java";
```

Có thể viết đơn giản:

```java
String name = "Java";
```

Không phải mọi phép ép kiểu đều dư thừa. Một số phép ép kiểu có ý nghĩa tại ranh giới kiểu hoặc khi làm rõ overload. Cần đọc thông điệp cụ thể trước khi xóa, đặc biệt trong biểu thức generic hoặc API có nhiều overload.

### 3.7. `fallthrough`: switch có thể chạy xuyên qua case

Trong switch dạng truyền thống, nếu một nhánh không có `break`, `return` hoặc cấu trúc kết thúc tương ứng, chương trình có thể tiếp tục chạy vào nhánh tiếp theo.

```java
switch (status) {
    case NEW:
        prepare();
    case READY:
        execute();
        break;
    default:
        reject();
}
```

Nếu không chủ ý chạy xuyên qua, cần thêm `break` hoặc dùng switch expression/syntax phù hợp. Nếu fall-through là chủ ý, hãy thể hiện rõ trong code bằng comment và kiểm tra cảnh báo của compiler để người đọc hiểu luồng điều khiển.

### 3.8. `varargs`: lời gọi generic với varargs có thể không an toàn

Varargs kết hợp generic có thể tạo heap pollution trong một số trường hợp vì mảng được tạo ở runtime không giữ đầy đủ thông tin generic.

Ví dụ:

```java
import java.util.List;

class VarargsExample {
    static void printAll(List<String>... lists) {
        for (List<String> list : lists) {
            System.out.println(list);
        }
    }
}
```

Compiler có thể cảnh báo về varargs không reifiable hoặc heap pollution. Nếu phương thức thực sự an toàn, có thể xem xét `@SafeVarargs` trong những trường hợp Java cho phép và khi người viết chứng minh được method không làm lộ hoặc thay đổi mảng varargs theo cách gây mất an toàn. Annotation này là cam kết của lập trình viên, không phải phép kiểm tra tự động của compiler.

### 3.9. `overloads`, `overrides`, `static` và các nhóm khác

Một số lint key cảnh báo về overload có khả năng gây nhầm lẫn, khai báo override không đúng ý định hoặc gọi thành viên static qua một instance. Ví dụ:

```java
class Parent {
    void execute() {}
}

class Child extends Parent {
    @Override
    void execute() {}
}
```

Annotation `@Override` giúp compiler xác nhận method thực sự override method của superclass hoặc interface. Nếu vô tình sai tên hoặc sai chữ ký, compiler sẽ báo lỗi thay vì để lại một method mới không được gọi như dự kiến.

Các nhóm cảnh báo khác có thể liên quan đến class file, đường dẫn classpath, module, annotation processing, phép chia cho zero có thể nhận biết, biểu thức rỗng, `finally`, synchronization hoặc preview feature. Không phải JDK nào cũng có cùng danh sách key. Hãy dùng `javac --help-lint` để tra cứu theo đúng compiler đang chạy.

## 4. Phân tích warning trong bối cảnh nâng cấp JDK

Khi nâng JDK, số lượng warning có thể tăng dù mã nguồn không thay đổi. Điều này có thể do compiler mới bổ sung chẩn đoán, thay đổi cách phân loại, nâng mức cảnh báo hoặc nhận diện việc sử dụng API đã deprecated/removal.

Không nên coi mọi warning mới là lỗi do JDK. Cần phân loại nguyên nhân:

| Nguồn cảnh báo | Dấu hiệu | Hướng điều tra |
|---|---|---|
| API deprecated/removal | Key `deprecation` hoặc `removal` | Xác định API thay thế và phiên bản dự kiến loại bỏ. |
| Generic không an toàn | Key `unchecked` hoặc `rawtypes` | Tìm raw type, cast và ranh giới dữ liệu không có type. |
| Cấu trúc mã dễ sai | Key như `fallthrough`, `cast`, `finally` | Xác nhận logic có chủ ý hay là lỗi tiềm ẩn. |
| Serialization | Key `serial` | Kiểm tra serialized form và tương thích dữ liệu cũ. |
| Cấu hình compiler | Key `options`, `path`, `processing` hoặc nhóm tương ứng | Kiểm tra classpath, processor, plugin và cờ compiler. |
| Mã được sinh tự động | Warning trỏ đến generated source | Xác định generator, cấu hình hoặc phiên bản thư viện tạo mã. |
| Thay đổi từ dependency | Warning xuất hiện sau khi nâng thư viện | Đối chiếu API mới, source của dependency và release notes. |

### 4.1. So sánh warning giữa JDK cũ và mới

Để biết cảnh báo nào thực sự mới xuất hiện, hãy chạy build với cùng source code, cùng dependency và cấu hình lint trên hai compiler nếu có thể. Sau đó so sánh danh sách warning theo file, dòng, lint key và thông điệp.

Nếu thay đổi nhiều thành phần cùng lúc, cần ghi lại phiên bản compiler và dependency trong mỗi lần chạy. Nếu không, rất khó xác định warning đến từ compiler mới hay từ source của dependency vừa nâng cấp.

### 4.2. Ưu tiên warning có rủi ro cao

Không phải warning nào cũng có mức độ nghiêm trọng như nhau. Có thể ưu tiên theo thứ tự:

1. Cảnh báo API bị đánh dấu `forRemoval = true` hoặc API sắp bị loại bỏ.
2. Cảnh báo unchecked/raw type ở đường xử lý dữ liệu quan trọng.
3. Cảnh báo có thể chỉ ra lỗi logic như fall-through ngoài ý muốn hoặc phép ép kiểu sai.
4. Cảnh báo serialization ở hệ thống có lưu trữ hoặc trao đổi serialized object.
5. Cảnh báo cấu hình build, annotation processor và classpath.
6. Cảnh báo chất lượng hoặc phong cách ít có khả năng ảnh hưởng runtime.

Thứ tự này chỉ là gợi ý để phân loại. Mức ưu tiên thực tế còn phụ thuộc vào nơi code được sử dụng, mức độ quan trọng của dữ liệu và khả năng kích hoạt lỗi.

## 5. Chính sách xử lý cảnh báo trong dự án

Một chính sách tốt cần thống nhất cách phát hiện, phân loại, sửa, ngoại lệ và ngăn cảnh báo mới. Nếu mỗi lập trình viên tự chọn cờ compiler hoặc tự suppress warning, kết quả build giữa máy cá nhân và CI có thể khác nhau.

### 5.1. Bật lint theo mức độ phù hợp

Có thể bắt đầu bằng các nhóm quan trọng:

```bash
javac -Xlint:deprecation,removal,unchecked,rawtypes,serial Example.java
```

Khi đã hiểu số lượng và loại cảnh báo, có thể mở rộng:

```bash
javac -Xlint:all Example.java
```

Không nhất thiết mọi module phải áp dụng ngay một tập warning giống nhau nếu chúng có đặc thù khác nhau. Tuy nhiên, các module cùng loại nên dùng chính sách nhất quán và được cấu hình tập trung để dễ theo dõi.

### 5.2. Sửa nguyên nhân thay vì chỉ làm mất thông báo

Với từng warning, cần xác định nguyên nhân gốc:

- Deprecated: chuyển sang API được hỗ trợ và kiểm tra lại hành vi.
- Removal: ưu tiên thay thế trước khi nâng đến phiên bản loại bỏ API.
- Unchecked/raw type: bổ sung generic hoặc kiểm tra kiểu tại ranh giới dữ liệu.
- Serial: xác định có cần serialized form ổn định hay không và khai báo UID phù hợp.
- Fall-through: sửa luồng điều khiển hoặc ghi rõ chủ ý nếu thật sự cần.
- Cast: loại bỏ phép ép kiểu dư thừa hoặc kiểm tra lại kiểu và hợp đồng đầu vào.

Không nên thêm `@SuppressWarnings` trước khi hiểu vì sao compiler cảnh báo. Suppression chỉ làm compiler ngừng hiển thị cảnh báo; nó không sửa nguyên nhân.

### 5.3. Suppress warning trong phạm vi nhỏ nhất

Trong một số trường hợp, warning không thể tránh được vì phải tương tác với API legacy hoặc dữ liệu bên ngoài. Khi đó, có thể dùng `@SuppressWarnings` nhưng cần giới hạn ở method hoặc đoạn code nhỏ nhất có thể.

Ví dụ:

```java
@SuppressWarnings("unchecked")
private List<String> convertLegacyList(List<?> values) {
    // Chỉ an toàn nếu caller và kiểm tra dữ liệu bảo đảm mọi phần tử là String.
    for (Object value : values) {
        if (!(value instanceof String)) {
            throw new IllegalArgumentException("Expected String value");
        }
    }

    return (List<String>) values;
}
```

Trong ví dụ, suppression được đặt tại method có ranh giới kiểm tra rõ ràng. Tuy vậy, nếu có thể tạo một danh sách mới và chuyển từng phần tử sang `String`, cách đó thường dễ chứng minh an toàn hơn việc ép kiểu toàn bộ collection.

Khi suppress, nên ghi rõ:

- Lint key nào được suppress.
- Vì sao không thể sửa theo cách thông thường.
- Điều kiện nào làm thao tác được xem là an toàn.
- Test hoặc kiểm tra nào bảo vệ giả định đó.
- Khi nào cần xem xét loại bỏ suppression.

Tránh `@SuppressWarnings("all")` trên cả class hoặc package vì nó che khuất cả những cảnh báo mới mà nhóm chưa từng đánh giá.

### 5.4. Thiết lập baseline cho cảnh báo cũ

Một codebase lâu năm có thể đang có nhiều warning. Nếu bật toàn bộ lint rồi yêu cầu sửa tất cả trong một lần nâng JDK, công việc migration có thể bị kéo dài và khó phân biệt lỗi mới với nợ kỹ thuật cũ.

Có thể tạo baseline gồm các warning hiện hữu đã được phân loại, kèm file, key, lý do và người phụ trách. Sau đó đặt chính sách không cho số lượng hoặc danh sách warning tăng thêm. Khi sửa một warning cũ, xóa mục tương ứng khỏi baseline.

Baseline cần được rà soát định kỳ. Không nên lưu danh sách suppression vô thời hạn hoặc chấp nhận warning mới chỉ vì chúng xuất hiện trong một module vốn đã có nhiều cảnh báo.

### 5.5. Quy định thời điểm dùng `-Werror`

Tùy chọn `-Werror` yêu cầu compiler coi warning như lỗi biên dịch. Nếu một warning được phát ra trong lần compile đó, build có thể thất bại.

Ví dụ:

```bash
javac -Xlint:all -Werror Example.java
```

Đây là chính sách nghiêm ngặt và hữu ích để ngăn cảnh báo mới. Tuy nhiên, nên áp dụng sau khi đã:

1. Bật lint và thu thập baseline.
2. Phân loại cảnh báo theo mức độ và nguồn phát sinh.
3. Sửa warning có rủi ro cao.
4. Xử lý hoặc suppress có lý do các warning còn lại.
5. Xác nhận mã nguồn được sinh tự động và annotation processor không tạo ra lượng warning ngoài dự kiến.
6. Chạy build trên cùng cấu hình ở máy phát triển và CI.

Với codebase lớn, có thể bật `-Werror` trước cho module mới hoặc module đã sạch warning, rồi mở rộng dần. Điều quan trọng là chính sách phải rõ ràng: warning nào chặn build, ngoại lệ nằm ở đâu và ai có trách nhiệm xử lý.

## 6. Cấu hình `-Xlint` trong Gradle và Maven

Không nên chỉ chạy `javac` thủ công rồi để cấu hình build chính không có lint. Hãy đưa chính sách vào công cụ build mà nhóm sử dụng để CI và mọi máy phát triển có cùng hành vi.

### 6.1. Gradle với Groovy DSL

Có thể cấu hình cho mọi task `JavaCompile`:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll([
        '-Xlint:deprecation',
        '-Xlint:removal',
        '-Xlint:unchecked',
        '-Xlint:rawtypes',
        '-Xlint:serial'
    ])
}
```

Khi module đã xử lý warning và muốn áp dụng chính sách chặn build:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.addAll([
        '-Xlint:all',
        '-Werror'
    ])
}
```

Không nhất thiết phải khai báo cả hai đoạn cùng lúc. Chọn một cấu hình thống nhất theo giai đoạn của dự án. Nếu dùng convention plugin, nên đặt chính sách ở nơi quản lý các Java compile task để module không tự cấu hình lệch nhau.

### 6.2. Maven Compiler Plugin

Có thể truyền lint options qua `compilerArgs`:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <configuration>
        <showWarnings>true</showWarnings>
        <compilerArgs>
            <arg>-Xlint:deprecation</arg>
            <arg>-Xlint:removal</arg>
            <arg>-Xlint:unchecked</arg>
            <arg>-Xlint:rawtypes</arg>
            <arg>-Xlint:serial</arg>
        </compilerArgs>
    </configuration>
</plugin>
```

Khi muốn coi warning là lỗi, thêm compiler argument:

```xml
<compilerArgs>
    <arg>-Xlint:all</arg>
    <arg>-Werror</arg>
</compilerArgs>
```

Hãy kiểm tra phiên bản Maven Compiler Plugin và JDK toolchain thực tế. Nếu plugin chạy compiler khác với JDK mặc định của shell, lint key và warning có thể khác nhau.

### 6.3. Giữ cấu hình local và CI đồng nhất

Các tùy chọn lint cần nằm trong build script hoặc convention plugin được version control. Tránh chỉ cấu hình trong IDE hoặc biến môi trường cá nhân, vì CI có thể không chạy cùng bộ cảnh báo.

Nếu có nhiều JDK trong pipeline, ghi lại compiler thực tế của từng task. Có thể build/test trên JDK nguồn và JDK đích để so sánh, nhưng phải giữ rõ mục đích của mỗi job: kiểm tra tương thích ngược, kiểm tra migration hay xác minh artifact phát hành.

## 7. Xây dựng chính sách cảnh báo theo từng giai đoạn

Không có một cấu hình duy nhất phù hợp với mọi codebase. Có thể tổ chức chính sách theo các giai đoạn sau.

### Giai đoạn 1: Quan sát

Bật các nhóm cảnh báo phù hợp, lưu output của compiler và xác định warning nào đã tồn tại. Chưa nên bật `-Werror` toàn dự án nếu chưa biết ảnh hưởng đến mã nguồn cũ, generated source và dependency.

Mục tiêu của giai đoạn này là có baseline đáng tin cậy, không phải làm cho build xanh bằng mọi cách.

### Giai đoạn 2: Phân loại và ưu tiên

Phân loại theo lint key, module, file và mức độ rủi ro. Xác định warning đến từ source do nhóm sở hữu, mã được sinh tự động hay tương tác với thư viện legacy. Chọn những warning có nguy cơ ảnh hưởng runtime hoặc migration để xử lý trước.

### Giai đoạn 3: Sửa warning và ghi nhận ngoại lệ

Sửa nguyên nhân khi có thể. Nếu phải giữ warning, giới hạn suppression ở phạm vi nhỏ và ghi rõ lý do cùng điều kiện an toàn. Các warning còn tồn tại phải có owner hoặc kế hoạch xử lý, đặc biệt với API removal.

### Giai đoạn 4: Ngăn phát sinh warning mới

Khi baseline đã ổn định, áp dụng `-Werror` cho module sạch hoặc cho nhóm warning đã được xử lý. Nếu không thể bật toàn bộ `-Xlint:all` ngay, có thể bật các key quan trọng trước và mở rộng theo từng đợt.

### Giai đoạn 5: Duy trì trong CI và review

CI phải chạy cùng cấu hình lint. Khi warning mới xuất hiện, pull request cần giải thích nguyên nhân, sửa warning hoặc thêm ngoại lệ có căn cứ. Định kỳ xem lại baseline và bỏ suppression không còn cần thiết.

## 8. Những điều `-Xlint` không thể thay thế

`-Xlint` hữu ích nhưng phạm vi vẫn là chẩn đoán compiler. Không nên dùng số lượng warning làm thước đo duy nhất về độ an toàn của migration.

- **Không chứng minh tương thích nhị phân:** source compile thành công không bảo đảm các JAR/plugin cũ liên kết được. Cần kiểm thử artifact đã phát hành và phân tích API.
- **Không chứng minh tương thích hành vi:** compiler không biết đầy đủ hợp đồng nghiệp vụ. Cần regression test, contract test và kiểm tra dữ liệu.
- **Không phát hiện mọi lỗi runtime:** reflection, class loading động, TLS, native library, memory pressure và race condition cần kiểm thử ở runtime.
- **Không thay thế static analysis:** các công cụ phân tích chuyên biệt có thể phát hiện nullability, injection, concurrency hoặc lỗi bảo mật nằm ngoài phạm vi compiler.
- **Không đánh giá hiệu năng:** cần benchmark và kiểm thử tải đại diện trên môi trường mục tiêu.

Có thể kết hợp `-Xlint` với các công cụ khác. Chẳng hạn, `jdeprscan` hỗ trợ rà soát việc sử dụng API deprecated trong class file; công cụ phân tích API như Revapi hoặc japicmp giúp so sánh hai phiên bản thư viện. Mỗi công cụ có giới hạn riêng và cần được dùng cùng kiểm thử phù hợp.

## 9. Ví dụ quy trình xử lý warning khi nâng JDK

Giả sử một dự án đang dùng JDK cũ và chuyển compiler sang JDK mới. Sau khi bật `-Xlint:all`, CI ghi nhận các warning sau:

| Warning | Phân tích ban đầu | Hành động |
|---|---|---|
| `[deprecation]` | Code gọi API cũ vẫn còn được cung cấp nhưng đã có API thay thế | Đọc Javadoc và migration guide, chuyển API rồi chạy regression test. |
| `[removal]` | API được đánh dấu dự kiến loại bỏ | Ưu tiên thay thế trước khi chuyển sang JDK loại bỏ API. |
| `[unchecked]` | Cast generic không được compiler kiểm tra đầy đủ | Sửa generic hoặc kiểm tra dữ liệu tại ranh giới. |
| `[rawtypes]` | Dùng collection không khai báo tham số kiểu | Chuyển sang generic cụ thể và kiểm tra consumer. |
| `[serial]` | Serializable class thiếu UID | Xem có cần tương thích serialized data cũ không, sau đó định nghĩa UID và kiểm thử dữ liệu. |

Nhóm không nên thêm `-Werror` ngay sau lần build đầu tiên. Trước tiên, cần xác nhận mỗi warning có phải mới xuất hiện do compiler hay đã tồn tại từ trước. Sau khi sửa và ghi nhận ngoại lệ, chạy lại toàn bộ build trên JDK mục tiêu. Khi baseline ổn định, bật `-Werror` để các warning mới làm CI thất bại.

Nếu warning đến từ generated source, hãy kiểm tra generator hoặc annotation processor. Không nên suppress cả package generated một cách rộng rãi nếu vẫn có thể sửa template hoặc nâng phiên bản generator.

## 10. Checklist thiết lập chính sách warning

- [ ] Đã xác định chính xác compiler và JDK dùng trong build.
- [ ] Đã chạy `javac --help-lint` để biết các key được phiên bản compiler hỗ trợ.
- [ ] Đã chọn nhóm warning phù hợp với giai đoạn migration.
- [ ] Đã lưu baseline warning hiện hữu theo file, lint key và thông điệp.
- [ ] Đã phân biệt warning mới với warning đã tồn tại.
- [ ] Đã ưu tiên xử lý `removal`, `deprecation`, `unchecked` và các cảnh báo ảnh hưởng logic/dữ liệu.
- [ ] Đã sửa nguyên nhân trước khi cân nhắc suppression.
- [ ] Mỗi `@SuppressWarnings` có phạm vi nhỏ và lý do rõ ràng.
- [ ] Generated source và annotation processor đã được kiểm tra riêng.
- [ ] Cấu hình lint được lưu trong build script/convention plugin và chạy giống nhau ở CI.
- [ ] Đã xác định thời điểm và phạm vi áp dụng `-Werror`.
- [ ] Đã kết hợp lint với kiểm thử runtime, binary compatibility và regression test.

## 11. Kết luận

`-Xlint` giúp compiler đưa ra cảnh báo chi tiết về những cấu trúc mã có thể gây lỗi, khó bảo trì hoặc phụ thuộc vào API không còn được khuyến nghị. Khi nâng JDK, các cảnh báo mới là tín hiệu cần điều tra: chúng có thể chỉ ra API deprecated/removal, generic không an toàn, raw type, serialization thiếu kiểm soát hoặc cấu trúc điều khiển đáng ngờ.

Chính sách phù hợp cần bật lint có chủ đích, phân loại warning, sửa nguyên nhân, ghi nhận suppression hẹp và duy trì baseline. `-Werror` nên được áp dụng khi nhóm đã kiểm soát được cảnh báo hiện hữu để ngăn vấn đề mới đi vào codebase. Kết hợp những bước này với kiểm thử source, binary và hành vi sẽ giúp quá trình nâng cấp JDK có tín hiệu rõ ràng và có thể duy trì lâu dài.
