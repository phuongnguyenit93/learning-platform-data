# Giới hạn pointcut theo phạm vi gói, mô-đun hoặc thành phần trong AOP

**Pointcut** là quy tắc lựa chọn những điểm can thiệp (*join points*) nơi hành vi bổ sung (*advice*) của một khía cạnh (*aspect*) được áp dụng. Bài toán thực tế không chỉ là “chạy advice khi nào?” mà còn là **“chính xác phần nào của chương trình được phép chịu ảnh hưởng?”**. Một chính sách đo thời gian chỉ dành cho tầng xử lý đơn hàng không nên vô tình chạy trong mã dựng đối tượng, thư viện ngoài hoặc thành phần tính toán chuyên sâu không liên quan.

Giới hạn pointcut theo **gói (package)**, **mô-đun (module)** hoặc **thành phần (component)** giúp biểu đạt biên áp dụng, giảm can thiệp ngoài ý muốn và làm rõ nơi sở hữu chính sách. Tuy nhiên, phạm vi **khớp theo quy tắc** và phạm vi **thực sự được cơ chế AOP can thiệp** là hai điều phải kiểm tra riêng. Cú pháp pointcut, loại join point hỗ trợ và cách weaving phụ thuộc công nghệ cụ thể.

## 1. Sau bài này cần hiểu gì?

- Vì sao pointcut càng rộng càng dễ tạo tác dụng phụ và vì sao pointcut quá hẹp dễ bỏ sót hành vi cần quan sát.
- Cách xây dựng điều kiện phạm vi theo tên package, lớp/kiểu, mô-đun logic hoặc thành phần có hợp đồng rõ ràng.
- Phân biệt package Java, mô-đun theo kiến trúc và mô-đun Java Platform Module System (JPMS); tránh suy luận nhầm cơ chế đóng gói thành ngôn ngữ pointcut.
- Phân biệt vị trí **mã chứa join point** với **kiểu/đối tượng đích** và **người gọi**, vì ba cách lọc có thể cho kết quả khác nhau.
- Ghép điều kiện phạm vi với điều kiện thao tác, chẳng hạn thực thi phương thức xử lý yêu cầu, thay vì chỉ dựa vào tên package.
- Hiểu các giới hạn của proxy, weaving bytecode, đường gọi nội bộ, quyền truy cập và khả năng kiểm thử.
- Tự kiểm tra phạm vi qua ví dụ Java 17 và ma trận ca thành công, ngoài phạm vi, đường gọi đi vòng và thay đổi kiến trúc.

## 2. Tư duy nền: chọn đúng điểm, đúng phần chương trình

Giả sử một ứng dụng gồm:

```text
app
├── catalog          (tra cứu sản phẩm)
├── order            (xử lý đơn hàng)
│   ├── application  (điều phối tác vụ)
│   └── domain       (quy tắc kinh doanh)
├── payment          (tương tác thanh toán)
├── reporting        (báo cáo)
└── observability    (theo dõi kỹ thuật)
```

Đây là **sơ đồ mô-đun kiến trúc**, chưa khẳng định mỗi nhánh phải là một Java package hoặc một JPMS module.

Ta muốn ghi thời lượng những thao tác thuộc `order.application`, không đo mọi phép tính trong `order.domain` và không ghi các thao tác báo cáo. Một pointcut phù hợp phải biểu đạt được hai lớp điều kiện:

1. **Loại join point nào?** Ví dụ, thực thi một phương thức mà cơ chế AOP hỗ trợ.
2. **Join point thuộc phạm vi nào?** Ví dụ, phương thức trong một nhóm kiểu xử lý tác vụ đơn hàng.

Chỉ biết một thành phần “thuộc order” chưa đủ: bên trong đó có thể có phương thức nội bộ chạy hàng triệu lần; áp advice cho mọi điểm có thể tạo chi phí và dữ liệu theo dõi rất lớn.

### 2.1. Pointcut, advice và weaving làm ba việc khác nhau

| Khái niệm | Trách nhiệm |
| --- | --- |
| **Join point** | Điểm thực thi có thể can thiệp theo mô hình AOP đang dùng |
| **Pointcut** | Chọn tập join point thông qua điều kiện về loại thao tác, kiểu, tên, phạm vi hoặc bối cảnh |
| **Advice** | Hành vi thực hiện trước, sau hoặc bao quanh điểm được chọn, tùy công nghệ |
| **Aspect** | Đóng gói chính sách gồm pointcut cùng hành vi bổ sung |
| **Weaving / kết hợp lúc chạy** | Đưa chính sách vào đường thực thi tại các điểm đã chọn và hỗ trợ được |

Ví dụ pointcut “các lần thực thi phương thức công khai trong nhóm xử lý đơn hàng” là **bộ lọc**. Nó chưa nói phải in log, đo thời gian hay kiểm tra quyền; điều đó thuộc advice. Đồng thời, chỉ khai báo pointcut không bảo đảm chương trình chạy advice: mã hoặc lời gọi phải thật sự đi qua cơ chế kết hợp.

### 2.2. Phạm vi áp dụng khác quyền truy cập

Một package hay JPMS module giúp tổ chức và kiểm soát một số quan hệ truy cập mã nguồn. Điều kiện pointcut chỉ mô tả **nơi chọn hành vi AOP**. Nó không tự trở thành ranh giới bảo mật, ranh giới giao dịch hoặc bộ kiểm soát quyền bắt buộc. Nếu có đường thực thi không được can thiệp, chính sách có thể không chạy ở đường đó.

## 3. Giới hạn theo package

Trong Java, câu lệnh `package` xác định gói của một kiểu. Ví dụ:

```java
package example.order.application;

public final class SubmitOrderService {
    public void submit() {
        // Logic điều phối đơn hàng.
    }
}
```

Một chính sách có thể chọn join point nằm trong các kiểu thuộc `example.order.application`. Điểm cần xác định là **chỉ gói chính xác đó** hay **cả các gói con** như `example.order.application.internal`.

### 3.1. Gói chính xác và cây gói con

Hai kiểu điều kiện thường cần phân biệt:

- **Exact package:** chỉ những kiểu nằm trực tiếp trong `example.order.application`.
- **Package subtree:** những kiểu thuộc `example.order.application` và các gói bắt đầu bằng `example.order.application.`.

Trong Java, `example.order.application.internal` là **gói riêng**, không phải thành viên của gói `example.order.application` theo nghĩa quyền truy cập package-private. Quan hệ tên theo dấu chấm có ích cho quy ước tổ chức và biểu thức chọn, nhưng không tạo tự động quan hệ kế thừa quyền giữa hai package.

Cũng đừng lọc bằng tiền tố thiếu dấu chấm:

```java
name.startsWith("example.order")
```

Biểu thức ấy còn chọn cả `example.ordersystem`. Nếu muốn gồm package gốc và gói con, mô tả đúng là:

```java
name.equals("example.order") || name.startsWith("example.order.")
```

Đây là **điều kiện chuỗi Java minh họa**, không phải cú pháp pointcut chuẩn của mọi công nghệ AOP.

### 3.2. Lọc nơi định nghĩa kiểu, nơi chạy hay nơi gọi?

Giả sử mã trong `example.order.application` gọi `example.payment.PaymentClient.charge()`.

Một điều kiện “join point nằm **bên trong mã của order.application**” có thể chọn điểm **lời gọi** `charge()` ở phía order, nếu mô hình hỗ trợ *method call join point*. Một điều kiện “thực thi phương thức của kiểu **PaymentClient**” lại xét phía phương thức đích, thuộc payment. Hai điều kiện khác nhau dù cùng tham gia một lời gọi.

Bởi vậy phải xác định:

- **Vị trí từ vựng của join point:** bytecode/mã chứa điểm thực thi thuộc loại nào và nằm ở đâu?
- **Kiểu khai báo phương thức/field:** thành phần nào định nghĩa thành viên đang được gọi hoặc truy cập?
- **Kiểu thực của đối tượng:** đối tượng được gọi có thể là lớp con, lớp ủy quyền hoặc proxy thuộc package khác.
- **Người gọi:** điểm phát sinh lời gọi có thể nằm ngoài package của thành phần đích.

Một biểu thức chỉ dựa trên `target.getClass().getPackageName()` lọc theo **lớp runtime đích**; nó không đồng nghĩa chọn mọi join point được viết bên trong một package. Nhiều lỗi phạm vi bắt đầu từ việc nhầm hai khái niệm này.

### 3.3. Ví dụ cú pháp điểm chọn trong một mô hình AOP cụ thể

Một số ngôn ngữ pointcut, chẳng hạn ngôn ngữ của AspectJ, có khái niệm như `within` và `execution`. Hai biểu thức dưới đây **chỉ là minh họa cú pháp của mô hình đó**, không phải Java độc lập và không phải cú pháp chung áp dụng cho mọi công cụ:

```text
within(example.order.application..*)
execution(* example.order.application..*.*(..))
```

Về ý tưởng:

- `within(example.order.application..*)` chọn join point có **vị trí từ vựng** bên trong những kiểu thuộc gói/cây gói được chỉ định, theo ngữ nghĩa của công cụ.
- `execution(* example.order.application..*.*(..))` chọn những join point **thực thi phương thức** khớp kiểu và mẫu tên/chữ ký. Đây là tập điểm có loại thao tác cụ thể hơn.

Ký hiệu `..` có ý nghĩa riêng trong ngôn ngữ mẫu kiểu này; không nên đem nó sang biểu thức Java `startsWith` hay một hệ pointcut khác mà chưa kiểm chứng cú pháp.

Điều kiện chọn theo package **không nhất thiết** chọn phương thức kế thừa hay những lớp proxy sinh động theo đúng ý định ban đầu. Hãy kiểm thử từng kiểu runtime và ranh giới gọi mà ứng dụng sử dụng.

### 3.4. Khi nào lọc theo package phù hợp?

Phù hợp khi package phản ánh **ranh giới kiến trúc được duy trì nhất quán**: ví dụ một gói chỉ chứa điểm vào ứng dụng mà mọi thao tác đều cần đo. Nếu cùng một chính sách áp cho các lớp ở nhiều package, một quy tắc theo vai trò hoặc hợp đồng có thể rõ hơn.

Không nên dùng tên package như điều kiện duy nhất nếu một gói vừa chứa API công khai, thuật toán nội bộ, mô hình dữ liệu và bộ phát sự kiện. Phạm vi đó quá rộng đối với nhiều loại advice.

## 4. Giới hạn theo mô-đun: cần định nghĩa “module”

Trong dự án thực tế, “mô-đun” có nhiều nghĩa:

| Cách dùng | Ví dụ | Ý nghĩa của ranh giới |
| --- | --- | --- |
| **Mô-đun logic/kiến trúc** | `order`, `payment`, `reporting` | Một nhóm trách nhiệm được tổ chức theo nghiệp vụ hoặc kỹ thuật |
| **Mô-đun build/artifact** | Một thư viện JAR riêng hoặc một dự án con build | Đơn vị biên dịch, đóng gói và phụ thuộc |
| **JPMS module** | `module example.orders { ... }` | Đơn vị module chính thức của Java với khai báo phụ thuộc và khả năng công khai package |
| **Đơn vị triển khai** | Một dịch vụ chạy thành tiến trình độc lập | Ranh giới tiến trình/mạng và vòng đời triển khai |

**Không mặc định** một điều kiện pointcut “theo module” hiểu được cả bốn nghĩa. Công cụ AOP có thể chỉ hiểu kiểu/package, hoặc cung cấp bộ lọc theo nguồn gốc lớp, module descriptor, class loader, artifact hay metadata riêng.

### 4.1. Mô-đun logic

Một mô-đun `order` có thể chứa nhiều package:

```text
example.order.api
example.order.application
example.order.domain
example.order.infrastructure
```

Giới hạn theo mô-đun logic có thể được hiện thực bằng:

- Một **nhóm package** có quy ước ổn định;
- Một **hợp đồng kiểu** chung cho các điểm vào được theo dõi;
- Metadata như annotation đánh dấu vai trò;
- Một danh sách rõ ràng các thành phần được phép áp chính sách;
- Quy tắc cấu hình của bộ weaving, nếu hỗ trợ.

Đây là những cách biểu đạt **cùng một biên kiến trúc**. Chọn cách phù hợp nhất với người quản lý module và độ ổn định của API. Không nên tạo một biểu thức khớp toàn bộ `example.order..` chỉ vì tên module là order, nếu thật ra chính sách chỉ áp cho API đầu vào.

### 4.2. JPMS module của Java

Java 9 trở lên cung cấp **Java Platform Module System (JPMS)**. Ví dụ một mô tả module đơn giản:

```java
module example.orders {
    exports example.orders.api;
}
```

Đây là tệp `module-info.java` **minh họa**, cần có package phù hợp và được biên dịch trong một bố cục module hợp lệ. `exports` cho phép các module khác truy cập các kiểu `public` trong package đã xuất theo luật JPMS; nó **không** có nghĩa mọi phương thức của package đó tự động được một aspect can thiệp.

Trong mã chạy trên JVM, có thể tra module runtime của một lớp bằng `SomeType.class.getModule()` và tên bằng `getName()`; tên có thể `null` với unnamed module. Đây là thông tin để xây dựng bộ lọc **khi cơ chế cho phép**, không phải một phép pointcut phổ quát.

Các khái niệm cần phân biệt:

- **`requires`** mô tả phụ thuộc module được đọc.
- **`exports`** công khai các kiểu `public` thuộc package cho module khác truy cập theo quy tắc module.
- **`opens`** liên quan đến khả năng reflection sâu đối với package được mở.
- **Weaving/instrumentation** có khả năng và điều kiện riêng; không suy ra “có exports là được weave” hoặc “không exports là bảo đảm không weave”.

Các công cụ biến đổi bytecode, reflection hay nạp lớp có thể chịu giới hạn quyền truy cập và module khác nhau. Cần kiểm tra tài liệu cụ thể và chạy thử với **cấu hình module path thực**, thay vì chỉ kiểm tra trong classpath.

### 4.3. Mô-đun build và ranh giới artifact

Một artifact độc lập giúp xác định lớp nào sẽ được biên dịch/đóng gói hoặc cung cấp cho weaver. Nhưng tên file JAR, tên dự án con hoặc thư mục nguồn không mặc định xuất hiện trong mô hình join point. Nếu cần áp aspect cho các lớp trong một artifact, phải cấu hình **phạm vi lớp được tải hoặc biến đổi**, rồi kiểm tra tập join point thực tế trong những lớp đó.

Có thể xảy ra tình huống một số lớp phụ thuộc được đóng gói chung, hoặc một lớp được nạp từ class loader khác, khiến “giới hạn theo JAR” và “giới hạn theo package” không trùng nhau.

### 4.4. Đơn vị triển khai

Nếu `payment` là dịch vụ khác tiến trình, weaving trong tiến trình `order` **không thể tự động can thiệp bytecode đang chạy trong tiến trình payment**. Ta có thể đo lời gọi HTTP hoặc RPC ở **phía client** của order, nhưng điều đó khác với việc đo trực tiếp mọi phương thức trong payment.

Khi qua ranh giới mạng, cần phân biệt pointcut trong mã của từng tiến trình với cơ chế truyền bối cảnh truy vết giữa các dịch vụ. Đây là lựa chọn kiến trúc; việc đặt tên hai service giống nhau không tạo một pointcut xuyên tiến trình.

## 5. Giới hạn theo thành phần hoặc vai trò

**Thành phần** ở đây là phần mềm có trách nhiệm/hợp đồng xác định: bộ xử lý lệnh, bộ kết nối ngoài, bộ tính giá, bộ ghi sự kiện. Một thành phần có thể là một lớp, nhóm lớp hoặc giao diện; không nhất thiết trùng với một package hoặc artifact.

Giới hạn theo vai trò thường bền hơn lọc tên gói khi kiến trúc hay tổ chức thư mục đổi.

### 5.1. Chọn theo giao diện hoặc kiểu

Giả sử các tác vụ đầu vào đều triển khai:

```java
public interface CommandHandler<C, R> {
    R handle(C command);
}
```

Đây là **đoạn mã minh họa**, không phải toàn bộ chương trình. Một cơ chế hỗ trợ lọc theo kiểu có thể chọn thực thi `handle` thuộc nhóm `CommandHandler` thay vì “mọi phương thức trong package application”. Ý nghĩa chính sách trở nên cụ thể: nó áp tại **ranh giới xử lý lệnh**.

Nhưng cần phân biệt:

- Cơ chế chọn theo **kiểu khai báo**, **kiểu runtime** hoặc quan hệ kế thừa nào?
- Nếu một lớp triển khai nhiều giao diện, phương thức nào được chọn?
- Khi có lớp ủy quyền/proxy, kiểu runtime có thay đổi điều kiện không?
- Nếu điểm được chọn là **method execution**, lời gọi nội bộ đến một phương thức khác có tự phát sinh điểm được hỗ trợ hay không?

Không nên suy ra chỉ từ việc `instanceof CommandHandler` là mọi lời gọi của đối tượng ấy đã được weave.

### 5.2. Chọn theo annotation/metadata

Một marker có thể biểu thị vai trò:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface ObservedComponent {}
```

Đây là **minh họa cho một kiểu marker**, cần đặt trong tệp `ObservedComponent.java` nếu biên dịch. Công cụ AOP có thể có quy tắc chọn dựa trên annotation, miễn là loại join point và cơ chế đọc metadata đó được hỗ trợ.

Annotation đánh dấu **ý định** áp một chính sách; nó không tự biến đổi mã hoặc bảo đảm lời gọi đi qua advice. Một lớp con, proxy sinh động hoặc thành phần được tạo không qua tuyến sử dụng mong đợi có thể cần kiểm chứng riêng.

### 5.3. Chọn theo danh sách thành phần rõ ràng

Nếu chính sách rất nhạy cảm, danh sách chính xác tên kiểu, chức năng hoặc cổng giao tiếp có thể dễ kiểm toán hơn bộ lọc tự động quá rộng. Đánh đổi là cần cập nhật danh sách khi thêm thành phần mới. Cách này hữu ích khi điểm áp dụng phải được phê duyệt từng trường hợp.

Tóm lại, chọn theo **package** trả lời “nằm ở khu vực mã nào?”, chọn theo **module** trả lời “thuộc đơn vị quản lý nào?”, còn chọn theo **component** trả lời “đóng vai trò gì?”. Một pointcut tốt thường kết hợp các tiêu chí ấy với điều kiện thao tác.

## 6. Kết hợp các điều kiện: phạm vi + loại thao tác + loại trừ

Một điều kiện phạm vi riêng lẻ có thể chưa đủ. Với chính sách đo thời gian, quy tắc mong muốn thường là:

```text
Chọn join point khi:
  1. Đây là thực thi phương thức được cơ chế hỗ trợ;
  2. Phương thức thuộc nhóm xử lý lệnh của module đặt hàng;
  3. Phương thức đại diện cho điểm vào cần đo;
  4. Không thuộc mã của chính hệ thống theo dõi;
  5. Không phải thành phần kỹ thuật nội bộ không liên quan.
```

Đó là **đặc tả logic**, không phải cú pháp dành cho một AOP framework cụ thể. Điều kiện Boolean có thể được xem như:

```text
SELECT = JOIN_POINT_KIND
         AND MODULE_SCOPE
         AND COMPONENT_ROLE
         AND INCLUDED_OPERATION
         AND NOT EXCLUDED_INTERNAL
```

Nhờ kết hợp, cùng một module có thể chứa nhiều thành phần nhưng chỉ các **điểm vào công khai** được can thiệp. Các điều kiện loại trừ còn giúp tránh tự ghi log khi chính bộ ghi log hoạt động.

### 6.1. Quy tắc bao gồm và loại trừ

Điều kiện **bao gồm** chỉ rõ tập điểm cần đo. Điều kiện **loại trừ** có thể bỏ qua mã tracing, hàm thao tác nền, phương thức đối tượng cơ bản hoặc đường gọi nhạy cảm.

Nhưng không nên bắt đầu với “mọi thứ” rồi loại trừ một danh sách kéo dài mãi. Nếu tập cần áp biết rõ, một biểu thức bao gồm hẹp và đặt tên theo vai trò thường dễ kiểm tra hơn.

### 6.2. Điểm quyết định tĩnh và điều kiện động

Điều kiện theo package, kiểu hoặc chữ ký thường có thể được đánh giá ở giai đoạn cấu hình hoặc weaving, tùy công nghệ. Điều kiện dựa trên **đối số, trạng thái đối tượng hoặc bối cảnh chạy** cần kiểm tra tại lúc thực thi.

Ví dụ: cùng một `CommandHandler` chỉ đo những lệnh có tùy chọn chẩn đoán bật. Khi đó, phần chọn theo vai trò có thể tĩnh; phần “có bật chẩn đoán không?” là động. Điều kiện động có thể tăng chi phí, đồng thời tạo nguy cơ lựa chọn khác nhau qua các lần chạy. Cần xác định rõ những gì phải được quan sát *luôn luôn* và những gì chỉ đo có điều kiện.

### 6.3. Đường gọi và phạm vi weaving quyết định kết quả cuối

Một mô tả pointcut có thể chọn đúng lớp nhưng vẫn **không chạy advice** nếu:

- Lớp hoặc join point nằm ngoài phạm vi bytecode được weaver xử lý;
- Đường gọi đi thẳng tới đối tượng đích thay vì qua proxy;
- Lời gọi nội bộ không vòng qua proxy của chính đối tượng đó;
- Điểm thao tác (field access, constructor, lời gọi private/static...) không được công nghệ hỗ trợ;
- Lớp đã được nạp trước khi bộ biến đổi tải lớp có hiệu lực;
- Cấu hình module, class loader hoặc quyền truy cập không cho phép cơ chế hoạt động như mong muốn.

**Matched scope ≠ effective interception.** Đây là sự khác biệt phải kiểm chứng trong chương trình thật.

## 7. Ví dụ Java 17: chỉ áp chính sách cho gói thanh toán

Ví dụ dưới đây dùng **JDK dynamic proxy** để mô phỏng một chính sách chỉ áp cho các thành phần trong gói `example.billing`. Đây là cơ chế bọc **lời gọi giao diện ở thời gian chạy**. Nó có ích để học cách diễn đạt *phạm vi*, nhưng **không phải bộ weaving có thể can thiệp mọi join point**.

Tạo cấu trúc tệp:

```text
src/
└── example/
    ├── Work.java
    ├── ScopeDemo.java
    ├── billing/
    │   └── ChargeWork.java
    └── reporting/
        └── ReportWork.java
```

### 7.1. Giao diện chung

Tệp `src/example/Work.java`:

```java
package example;

public interface Work {
    String execute();
}
```

### 7.2. Thành phần thuộc gói cần theo dõi

Tệp `src/example/billing/ChargeWork.java`:

```java
package example.billing;

import example.Work;

public final class ChargeWork implements Work {
    @Override
    public String execute() {
        return "Đã xử lý thanh toán";
    }
}
```

### 7.3. Thành phần ngoài phạm vi

Tệp `src/example/reporting/ReportWork.java`:

```java
package example.reporting;

import example.Work;

public final class ReportWork implements Work {
    @Override
    public String execute() {
        return "Đã tạo báo cáo";
    }
}
```

### 7.4. Áp dụng có điều kiện theo tên package

Tệp `src/example/ScopeDemo.java`:

```java
package example;

import example.billing.ChargeWork;
import example.reporting.ReportWork;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public final class ScopeDemo {
    private static boolean inBillingPackage(Class<?> type) {
        String name = type.getPackageName();
        return name.equals("example.billing")
                || name.startsWith("example.billing.");
    }

    private static Work monitorWhenInBilling(Work target) {
        if (!inBillingPackage(target.getClass())) {
            return target;
        }

        return (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(),
                new Class<?>[]{Work.class},
                (proxy, method, arguments) -> {
                    if (method.getDeclaringClass() == Work.class
                            && method.getName().equals("execute")) {
                        System.out.println("[TRACE] "
                                + target.getClass().getSimpleName());
                    }

                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        Work billing = monitorWhenInBilling(new ChargeWork());
        Work reporting = monitorWhenInBilling(new ReportWork());

        System.out.println(billing.execute());
        System.out.println(reporting.execute());
    }
}
```

Biên dịch/chạy từ thư mục chứa `src`, với Java 17 trở lên:

```bash
javac -encoding UTF-8 -d out src/example/Work.java src/example/billing/ChargeWork.java src/example/reporting/ReportWork.java src/example/ScopeDemo.java
java -cp out example.ScopeDemo
```

Kết quả:

```text
[TRACE] ChargeWork
Đã xử lý thanh toán
Đã tạo báo cáo
```

### 7.5. Phân tích ví dụ

1. `inBillingPackage` chỉ kiểm tra **package của lớp runtime**. Nó chấp nhận đúng `example.billing` hoặc cây package dưới đó và từ chối `example.reporting`.
2. `monitorWhenInBilling` tạo proxy cho `ChargeWork`. Với `ReportWork`, hàm trả về chính đối tượng đích, không tạo proxy và không có log.
3. Bộ lọc tên `execute` chỉ đóng vai trò mô phỏng điều kiện loại thao tác. Nó không chứng minh mọi method execution/call join point đã được chọn.
4. `InvocationTargetException` được bóc để chuyển tiếp nguyên nhân lỗi thật của phương thức đích.
5. Gọi trực tiếp `new ChargeWork().execute()` **không có** log vì không đi qua proxy. Lời gọi nội bộ trong lớp đích cũng không tự vòng qua proxy này.
6. Nếu một proxy được bọc thêm hoặc thành phần runtime là lớp sinh động trong package khác, điều kiện lọc theo **lớp runtime** có thể khác ý định lọc theo **lớp nghiệp vụ gốc**. Cần chọn rõ loại thông tin dùng để phân loại.
7. Nếu điều kiện trong ví dụ cần chuyển từ package sang vai trò giao diện hoặc annotation, phải thay **hàm quyết định đối tượng được bọc**; bản chất đường đi của proxy vẫn không đổi.

Ví dụ này nêu bật: phạm vi được xác định **trước khi tạo proxy**, nên “lớp ở đúng package” chưa đủ nếu người gọi không sử dụng proxy. Một bộ weaving trực tiếp vào mã lớp có thể có phạm vi khác, tùy cấu hình và loại điểm nối hỗ trợ.

## 8. Từ ví dụ sang mô hình AOP có pointcut đầy đủ hơn

Trong một mô hình hỗ trợ điều kiện **execution** và **within**, pointcut theo nhóm phương thức có thể biểu đạt mục tiêu rõ hơn:

```text
execution(* example.billing..*.*(..))
```

Đây là cú pháp biểu diễn theo ngôn ngữ pointcut của AspectJ, dùng **để minh họa**: lựa chọn các điểm thực thi phương thức khớp mẫu kiểu, tên và tham số trong cây package. Nó không phải Java và không được chạy bằng `javac`.

Nếu muốn giới hạn tới một điểm vào rõ hơn, có thể diễn giải quy tắc theo ý tưởng:

```text
Phương thức execution
AND loại xử lý tác vụ thanh toán
AND tên thao tác cần đo
AND NOT thuộc mã giám sát
```

Điều kiện kết hợp cần dùng đúng cú pháp của công cụ hiện thực. Không có biểu thức duy nhất cho mọi công nghệ AOP.

### 8.1. Khi chuyển từ package sang module

Nếu một module logic phân tán trên các package không chung tiền tố, thay lọc một cây package bằng **tập package được liệt kê**, hợp đồng kiểu hoặc metadata vai trò. Nếu ứng dụng có JPMS module, việc gắn thêm tiêu chí module runtime chỉ có hiệu lực khi bộ chọn có thể truy cập module và hỗ trợ điều kiện đó.

Đừng nhầm giữa “lấy tên module qua Java Reflection” và “mô hình weaving có bộ lọc theo module”. Đọc được metadata không đồng nghĩa weaver tự động sử dụng metadata ấy.

### 8.2. Khi chuyển từ module sang thành phần

Một thành phần `BillingGateway` có thể di chuyển package mà vai trò vẫn giữ nguyên. Lúc này pointcut theo giao diện hoặc annotation phù hợp hơn một chuỗi tên package cố định. Nhưng nếu thành phần có nhiều phương thức, vẫn phải chọn **phương thức nào**: đo ở ranh giới `charge()`, hay cả các phương thức kiểm tra/trợ giúp bên trong? Ranh giới hợp đồng nên được ưu tiên hơn “mọi phương thức của lớp này”.

## 9. Những vấn đề nâng cao về phạm vi

### 9.1. Một đối tượng có nhiều vai trò

Một lớp có thể vừa thực thi `CommandHandler`, vừa thực thi `HealthCheck`. Nếu pointcut chọn **toàn bộ đối tượng theo kiểu**, advice có thể áp lên các thao tác kiểm tra sức khỏe không liên quan. Điều kiện tốt hơn là chọn **vai trò + thao tác**.

Ngược lại, nếu một phương thức của lớp vừa thuộc nhóm phương thức xử lý lệnh vừa thuộc nhóm bảo trì, cần làm rõ mục đích nghiệp vụ thay vì cố suy luận hoàn toàn từ tên lớp.

### 9.2. Phân cấp kế thừa và kiểu khai báo

Khi một lớp con ở package A kế thừa phương thức khai báo ở package B, điều kiện theo **kiểu khai báo phương thức** và điều kiện theo **kiểu runtime đối tượng** có thể không giống nhau. Với override, bridge method do compiler sinh, generic hoặc lớp đại diện, số điểm và chữ ký được mô hình AOP nhận diện cũng có thể khác kỳ vọng.

Hãy kiểm thử bằng kiểu thực sự được gọi và điểm can thiệp mà cơ chế hỗ trợ. Không suy ra từ tên package của lớp con rằng mọi phương thức kế thừa được áp cùng chính sách.

### 9.3. Package và ranh giới độ tin cậy

Một chính sách kiểm soát quyền áp theo package không tự bảo vệ mọi đường gọi nếu có dịch vụ nội bộ, truy cập dữ liệu trực tiếp, reflection hoặc đường kết nối khác bỏ qua advice. **Bảo mật phải nằm ở ranh giới đáng tin cậy**, với quy tắc bảo vệ phù hợp; AOP có thể là cách tổ chức một phần cơ chế kiểm tra, nhưng chỉ khi mọi đường truy cập cần thiết được bao phủ.

Tên package, annotation hoặc tên module không được xem là chứng cứ người gọi được phép thực hiện hành động.

### 9.4. Giao thoa của nhiều aspect

Một nhóm phương thức có thể khớp cả aspect theo dõi toàn hệ thống và aspect kiểm toán riêng của module thanh toán. Nếu đều có around advice, thứ tự lồng nhau ảnh hưởng kết quả đo đạc và cách xử lý lỗi:

```text
Observe(Audit(Operation))
Audit(Observe(Operation))
```

Hai cấu trúc không luôn tương đương. Khi có retry, timeout, transaction hoặc kiểm tra quyền, thay thứ tự có thể thay đổi rõ hành vi. Quy tắc về thứ tự (precedence) cần được xác định theo cơ chế thực thi và kiểm thử trên đường thành công/lỗi.

### 9.5. Phạm vi code đã được weaving

Với compile-time/binary weaving, phải chắc chắn những lớp trong phạm vi mong đợi thực sự nằm trong sản phẩm được xử lý. Với load-time weaving, phải xác nhận lớp được tải sau khi bộ biến đổi có hiệu lực và không bị loại trừ. Với proxy, phải xác nhận tất cả người gọi mong đợi đều sử dụng đại diện.

Các giới hạn class loader, JPMS và quyền truy cập có thể khiến một lớp thuộc package hợp lệ về tên nhưng vẫn **không được can thiệp**. Vì vậy báo cáo “pointcut khớp 20 lớp” chưa chứng minh đã thực hiện advice tại 20 lớp đó.

### 9.6. Chi phí và lượng sự kiện

Nếu pointcut khớp một phương thức nội bộ được gọi hàng triệu lần, mỗi lần ghi log/đếm/truy vết có thể gây ảnh hưởng lớn. Giới hạn theo package **không tự đặt giới hạn tần suất**. Nên cân nhắc đo ở ranh giới nghiệp vụ hoặc dùng sampling phù hợp nếu chất lượng dữ liệu cho phép.

Lưu ý: sampling có thể chấp nhận được với số liệu hiệu năng, nhưng không tự nhiên phù hợp với kiểm toán bắt buộc hoặc quyết định an toàn. Cần phân biệt mục đích trước khi giảm số sự kiện.

### 9.7. Mã sinh, tên lại package và tái cấu trúc

Đổi package hoặc tách module có thể vô tình thêm/bớt các join point đang được áp dụng, dù nội dung phương thức không thay đổi. Một bộ lọc chỉ dựa trên tên có thể trở nên sai sau tái cấu trúc. Nếu gắn chính sách với một **hợp đồng ổn định**, hãy kiểm tra liệu ranh giới component có mô tả tốt hơn hay không.

Ngoài kiểm thử phương thức nghiệp vụ, cần có ca kiểm thử xác nhận những thành phần quan trọng được bao phủ sau mỗi thay đổi kiến trúc.

## 10. Cách thiết kế và kiểm chứng một pointcut có phạm vi

Hãy đi theo thứ tự:

1. **Xác định hành vi cần bảo đảm.** Ví dụ “đo một lần cho mỗi lệnh thanh toán ở điểm vào” khác “đo mọi phương thức trong thư viện thanh toán”.
2. **Chọn loại join point hỗ trợ được.** Method execution, method call, truy cập field hoặc loại khác, phụ thuộc mô hình AOP.
3. **Chọn biên kiến trúc.** Package chính xác, package subtree, module logic/JPMS/artifact hoặc vai trò component.
4. **Chọn điều kiện thao tác.** Chữ ký, kiểu khai báo, interface/annotation, tên hoặc tiêu chí động nếu thật sự cần.
5. **Định nghĩa loại trừ.** Tránh mã advice, đo lường nội bộ, thành phần phụ trợ hoặc đường gọi không liên quan.
6. **Xác minh khả năng weaving.** Những lớp nào thực sự bị biến đổi hoặc những lời gọi nào đi qua proxy?
7. **Kiểm thử đường áp dụng và đường không áp dụng.** Cả gọi thành công, lỗi, tự gọi nội bộ, nhiều lớp triển khai, đồng thời và tái cấu trúc.
8. **Kiểm soát tác dụng phụ.** Không nuốt lỗi, đổi kết quả, làm lặp thao tác hoặc ghi dữ liệu nhạy cảm nếu chính sách chỉ để quan sát.

### 10.1. Ma trận kiểm thử mẫu

| Tình huống | Kỳ vọng |
| --- | --- |
| Phương thức điểm vào đúng module/role | Advice chạy đúng số lần |
| Phương thức cùng package nhưng khác role | Không áp nếu role là điều kiện bắt buộc |
| Kiểu ở package con trong phạm vi đã chọn | Áp hoặc không theo quy tắc exact/subtree được tuyên bố |
| Package có tiền tố gần giống | Không khớp nhầm |
| Thành phần báo cáo ngoài module | Không áp advice của module thanh toán |
| Lời gọi đi trực tiếp tới đích trong cơ chế proxy | Thể hiện đúng giới hạn bypass |
| Phương thức kế thừa/override | Đúng quy tắc kiểu khai báo/kiểu thực |
| Artifact/lớp không được weaving | Được phát hiện thay vì nhầm là pointcut sai |
| Hai aspect cùng khớp | Thứ tự và lỗi đúng như hợp đồng |
| Tác vụ chạy đồng thời | Bối cảnh và số đo không lẫn nhau |

### 10.2. Dấu hiệu pointcut quá rộng hoặc quá hẹp

**Quá rộng** nếu log xuất hiện ở phương thức tiện ích nội bộ không liên quan, lặp nhiều lần trên một yêu cầu, đụng vào thư viện ngoài hoặc chứa thông tin nhạy cảm không cần thiết.

**Quá hẹp** nếu một implementation mới không có log, một đường gọi khác bỏ qua proxy, một package con bị loại không chủ ý hoặc chỉ một phần artifact được weaving.

Đừng sửa pointcut bằng cách thêm ký tự wildcard tùy tiện. Trước tiên phải xác định giới hạn là do **quy tắc chọn** hay do **khả năng kết hợp thực tế**.

## 11. Bài tập vận dụng

### Bài tập 1: Package cùng tiền tố

Bạn muốn chọn mọi kiểu trong `com.shop.order` và các gói con, nhưng không chọn `com.shop.ordering`. Vì sao `startsWith("com.shop.order")` chưa đúng? Viết điều kiện tên package phù hợp.

**Đáp án:** Tiền tố chưa có dấu chấm cho phép khớp `com.shop.ordering`. Một điều kiện minh họa hợp lệ trong Java là `name.equals("com.shop.order") || name.startsWith("com.shop.order.")`.

### Bài tập 2: Module và package

Module logic `shipping` gồm `app.shipping.api`, `app.shipping.domain` và `app.integrations.carriers`. Có thể chọn trọn module bằng `app.shipping..` không?

**Đáp án:** Không đủ: `app.integrations.carriers` nằm ngoài tiền tố. Cần mô hình module rõ, hợp đồng vai trò hoặc nhóm điều kiện package được liệt kê. Mẫu tên package không tự hiểu module logic.

### Bài tập 3: Vị trí gọi khác vị trí thực thi

Mã trong `app.order.application` gọi phương thức `app.payment.Client.send()`. Pointcut theo phạm vi *mã chứa lời gọi* trong order có giống pointcut chọn *thực thi của Client* trong payment không?

**Đáp án:** Không. Điểm call phía người gọi khác điểm execution phía đích; chúng có vị trí và khả năng hỗ trợ khác nhau. Phải chọn đúng loại join point và điều kiện phạm vi.

### Bài tập 4: Proxy bypass

Một proxy được tạo cho `BillingWork` thuộc package cần theo dõi, nhưng một người gọi vẫn giữ tham chiếu đối tượng gốc. Vì sao `original.execute()` không có log dù tên package đúng?

**Đáp án:** Bộ lọc package chỉ quyết định **có tạo proxy hay không**. Lời gọi qua tham chiếu gốc bỏ qua proxy, nên không được chặn. Cần thống nhất đường cung cấp đối tượng hoặc chọn cơ chế phù hợp nếu mọi đường gọi đều bắt buộc được can thiệp.

### Bài tập 5: JPMS và bảo mật

Một package được `exports` trong `module-info.java`. Điều đó có nghĩa mọi lời gọi trong package đều tự động có advice và được kiểm soát quyền không?

**Đáp án:** Không. `exports` thuộc quy tắc truy cập kiểu của JPMS; pointcut và weaving là cơ chế riêng. Kiểm soát quyền còn cần ranh giới đáng tin cậy và kiểm thử đường truy cập.

### Bài tập 6: Giao thoa chính sách

Một pointcut theo `payment` đo toàn bộ thời gian, còn pointcut theo `PaymentGateway` thực hiện retry. Bạn đặt `Timing(Retry(Operation))` hay `Retry(Timing(Operation))` nếu muốn đo tổng thời gian của cả chuỗi thử?

**Đáp án:** Dùng cấu trúc ý tưởng `Timing(Retry(Operation))` để đo toàn bộ chuỗi. Đo bên trong retry cho ra thời lượng của từng lần thử nếu advice được gọi mỗi lần. Cần kiểm tra thứ tự thực tế của cơ chế AOP và không retry bừa thao tác có tác dụng phụ.

## 12. Ghi nhớ

- Giới hạn pointcut theo **package, module hoặc component** là cách nói rõ *ở đâu* chính sách AOP được áp dụng; vẫn cần xác định **loại join point và thao tác**.
- **Package chính xác** khác **cây package con**; tên gần giống không tự thuộc cùng phạm vi.
- **Module logic, artifact, JPMS module và tiến trình triển khai** có ranh giới khác nhau; không được đồng nhất chúng.
- **Thành phần theo vai trò** (interface, annotation, hợp đồng cụ thể) có thể ổn định hơn tên package khi tái cấu trúc, nhưng vẫn phải chọn phương thức và đường thực thi.
- **Điều kiện pointcut khớp** chưa đủ: cơ chế weaving/proxy phải thực sự can thiệp vào đúng đường gọi.
- Pointcut tốt phải **đủ hẹp, có chủ đích, kiểm thử được và bảo toàn hợp đồng nghiệp vụ**, đặc biệt khi cùng vị trí chịu ảnh hưởng của nhiều aspect.
