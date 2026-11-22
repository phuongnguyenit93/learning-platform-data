# Kiểm tra phụ thuộc thật của giao diện công khai trong JPMS

Trong JPMS (Java Platform Module System), một mô-đun có thể phụ thuộc vào mô-đun khác để biên dịch và chạy. Tuy nhiên, không phải mọi phụ thuộc đều nên được truyền tiếp cho các mô-đun sử dụng API của nó. Điểm cần xác định là: **kiểu của mô-đun phụ thuộc có xuất hiện trong giao diện công khai mà client nhìn thấy hay chỉ được dùng bên trong phần triển khai?**

Phân biệt đúng hai trường hợp này giúp chọn giữa **requires** và **requires transitive**, tránh công khai phụ thuộc không cần thiết và giữ module graph gọn, dễ bảo trì.

Bài học dùng **jdeps** của JDK để phân tích phụ thuộc từ bytecode, kết hợp việc kiểm tra module descriptor và chữ ký API. Các lệnh được trình bày vẫn có trong JDK hiện hành.

## 1. Phụ thuộc triển khai và phụ thuộc API

Giả sử mô-đun A sử dụng mô-đun B.

- **Phụ thuộc triển khai (implementation dependency):** mã bên trong A gọi hoặc tạo đối tượng của B, nhưng các kiểu của B không xuất hiện trong API công khai của A. Client chỉ cần đọc A, không cần biết B để gọi API của A.
- **Phụ thuộc API (API dependency):** một kiểu của B xuất hiện trong chữ ký API công khai của A. Client muốn sử dụng API đó cũng cần đọc được B và package chứa kiểu đó phải được B export.

Ví dụ, nếu giao diện công khai có phương thức:

~~~java
public Customer findById(CustomerId id);
~~~

và **CustomerId** thuộc mô-đun B, thì B là một phần của hợp đồng API mà A công khai. Một client chỉ khai báo **requires A** vẫn cần đọc được kiểu **CustomerId** để biên dịch mã gọi phương thức này. Đây là trường hợp cần cân nhắc **requires transitive B** trong descriptor của A.

Ngược lại, nếu A chỉ dùng **AuditLogger** của B bên trong một lớp triển khai, còn API công khai chỉ nhận và trả về kiểu thuộc A hoặc JDK, thì B là phụ thuộc triển khai. A thường chỉ cần **requires B**.

## 2. Những vị trí có thể làm lộ phụ thuộc trong API

Khi kiểm tra một mô-đun, không chỉ tìm các câu lệnh import. Hãy xem các kiểu xuất hiện trong chữ ký của những lớp và thành viên mà client thực sự có thể truy cập.

Các vị trí cần rà soát gồm:

- Kiểu của trường public hoặc protected.
- Kiểu tham số và kiểu trả về của phương thức public hoặc protected.
- Kiểu ngoại lệ checked được khai báo trong throws.
- Lớp cha và interface mà kiểu công khai kế thừa hoặc triển khai.
- Các kiểu xuất hiện trong chữ ký generic, chẳng hạn kiểu phần tử của List hoặc giới hạn của type parameter.
- Các kiểu được tham chiếu bởi API công khai khác như constructor, nested type hoặc annotation trong hợp đồng API.

Với named module, cần xét thêm package chứa API có được export hay không. Một lớp public nằm trong package không export không tự động trở thành API thông thường cho các mô-đun khác. Vì vậy, hãy bắt đầu từ các package được export trong module-info.java, rồi kiểm tra chữ ký public/protected của các kiểu thuộc những package đó.

**Import không đồng nghĩa với API dependency.** Một import có thể chỉ phục vụ phần thân phương thức, biến cục bộ hoặc chi tiết triển khai. Ngược lại, một kiểu có thể bị lộ qua superclass, interface hoặc chữ ký generic dù việc tìm kiếm import đơn giản không cho thấy đầy đủ ý nghĩa của hợp đồng.

## 3. Khi nào dùng requires và requires transitive?

### 3.1. requires thông thường

Dùng **requires** khi mô-đun hiện tại cần đọc một mô-đun phụ thuộc để triển khai chức năng, nhưng không chủ định truyền khả năng đọc đó cho các mô-đun phụ thuộc vào mình.

~~~java
module com.example.service {
    requires com.example.audit;
    exports com.example.service.api;
}
~~~

Nếu các lớp trong phần triển khai của **com.example.service** gọi **AuditLogger**, khai báo trên là phù hợp khi kiểu **AuditLogger** không xuất hiện trong API công khai của service.

Client chỉ cần:

~~~java
module com.example.client {
    requires com.example.service;
}
~~~

Client không cần khai báo thêm **requires com.example.audit** chỉ để sử dụng API service, miễn là API đó không làm lộ kiểu của audit module.

### 3.2. requires transitive

Dùng **requires transitive** khi mô-đun hiện tại công khai các kiểu thuộc một mô-đun phụ thuộc và muốn client đọc mô-đun đó thông qua quan hệ phụ thuộc vào mô-đun hiện tại.

~~~java
module com.example.api {
    requires transitive com.example.model;
    exports com.example.api;
}
~~~

Khi mô-đun client khai báo **requires com.example.api**, module system cũng cho phép client đọc **com.example.model** thông qua cạnh phụ thuộc transitive.

Điều này giúp client sử dụng kiểu **CustomerId** xuất hiện trong chữ ký API của **com.example.api** mà không phải tự khai báo một phụ thuộc riêng chỉ để đọc kiểu đó.

### 3.3. Điều requires transitive không làm

**requires transitive** không export tất cả package của mô-đun phụ thuộc. Mô-đun B vẫn phải export package chứa kiểu mà client cần sử dụng.

Ví dụ, nếu API công khai của A trả về **com.example.model.CustomerId**, mô-đun B phải export package **com.example.model**. A phải đọc được B; client phải đọc được A và cần có khả năng đọc B. **requires transitive** trên A giải quyết phần truyền khả năng đọc, còn **exports** trên B giải quyết quyền truy cập package.

Nó cũng không biến các lớp triển khai private hoặc package nội bộ thành API công khai. Quyền truy cập vẫn chịu các quy tắc đóng gói và truy cập của Java.

### 3.4. Bảng quyết định

| Tình huống | Khai báo thường phù hợp | Lý do |
|---|---|---|
| Chỉ phần thân phương thức hoặc lớp nội bộ dùng kiểu B | **requires B** | B là phụ thuộc triển khai |
| API public/protected của A làm lộ kiểu B và client cần dùng kiểu đó | **requires transitive B** | B là phụ thuộc của hợp đồng API |
| A không làm lộ kiểu B; client không cần biết B | **requires B** | Không truyền phụ thuộc không cần thiết |
| API của A cố ý che giấu B bằng interface/DTO riêng của A | **requires B** thường đủ | Client chỉ làm việc với kiểu của A |

Không nên biến mọi **requires** thành **requires transitive** chỉ để tránh lỗi biên dịch ở một client cụ thể. Trước tiên hãy xác định client có thật sự cần đọc kiểu B vì kiểu đó thuộc API công khai của A hay không.

## 4. Quy trình kiểm tra phụ thuộc thật của API

Một quy trình thực tế có thể thực hiện theo các bước sau:

1. **Xác định module descriptor và package được export.** Ghi nhận các package là API của mô-đun, không đánh đồng mọi package trong artifact với API.
2. **Rà soát chữ ký public/protected.** Kiểm tra kiểu tham số, kiểu trả về, trường, superclass, interface, ngoại lệ và generic type.
3. **Chạy jdeps ở chế độ API-only.** Đối chiếu các phụ thuộc xuất hiện từ chữ ký public/protected với danh sách phụ thuộc tổng thể.
4. **Kiểm tra module descriptor.** Dùng **jdeps --check** để xem descriptor, kết quả phân tích phụ thuộc và đồ thị phụ thuộc sau khi rút gọn các cạnh đọc được suy ra.
5. **Thử một client độc lập.** Tạo mô-đun chỉ khai báo **requires A**, rồi biên dịch mã sử dụng API công khai của A. Nếu API cố ý làm lộ kiểu B, client phải đọc được B thông qua descriptor của A hoặc khai báo B trực tiếp theo thiết kế đã chọn.
6. **Quyết định phạm vi phụ thuộc.** Giữ **requires** cho chi tiết triển khai; dùng **requires transitive** khi B thực sự là một phần của hợp đồng API cần truyền cho client.

### 4.1. jdeps --api-only

**jdeps** phân tích phụ thuộc ở cấp class/package/module từ các tệp class, thư mục hoặc JAR. Tùy chọn **--api-only** giới hạn phân tích vào các phụ thuộc từ chữ ký của thành viên public và protected trong lớp public. Phạm vi này bao gồm kiểu trường, kiểu tham số, kiểu trả về và kiểu ngoại lệ checked.

Ví dụ với mô-đun đã biên dịch:

~~~bash
jdeps --api-only -verbose:class --module-path out --module com.example.api
~~~

Trong đó:

- **--api-only** chỉ phân tích các phụ thuộc từ API public/protected.
- **-verbose:class** hiển thị phụ thuộc ở cấp lớp để dễ xác định kiểu nào làm lộ mô-đun khác.
- **--module-path out** chỉ đường dẫn chứa các mô-đun cần phân tích và phụ thuộc của chúng.
- **--module com.example.api** chọn mô-đun gốc cần kiểm tra.

Nếu cần xem cả phụ thuộc được dùng bên ngoài chữ ký API, chạy thêm chế độ phân tích thông thường:

~~~bash
jdeps -verbose:class --module-path out --module com.example.api
~~~

So sánh hai kết quả giúp phân biệt phụ thuộc từ API với các tham chiếu chỉ xuất hiện trong phần triển khai. Kết quả API-only là tín hiệu để rà soát, không phải quyết định tự động rằng mọi mô-đun được liệt kê đều phải trở thành **requires transitive**.

### 4.2. jdeps --check

Dùng **--check** để kiểm tra descriptor và đồ thị phụ thuộc của một hoặc nhiều mô-đun:

~~~bash
jdeps --check com.example.api --module-path out
~~~

Kết quả cung cấp:

- Module descriptor hiện tại.
- Suggested module descriptor do công cụ phân tích.
- Transitive reduced graph, tức đồ thị đã lược bỏ các cạnh đọc được suy ra từ quan hệ transitive khác.

Lệnh này hữu ích để phát hiện descriptor chưa phản ánh đúng cấu trúc phụ thuộc và xem các cạnh đọc được thực tế. Tuy nhiên, nó không thay thế việc đọc chữ ký API và quyết định ranh giới công khai. Một phụ thuộc kỹ thuật có mặt trong module graph không mặc nhiên là một phần của hợp đồng API.

## 5. Ví dụ hoàn chỉnh: kiểm tra một API làm lộ kiểu từ mô-đun khác

Ví dụ gồm ba mô-đun:

- **com.example.model** cung cấp kiểu dữ liệu **CustomerId**.
- **com.example.api** công khai interface **CustomerService**, trong đó chữ ký phương thức dùng **CustomerId**.
- **com.example.client** chỉ phụ thuộc vào API nhưng vẫn cần sử dụng **CustomerId**.

Cấu trúc thư mục:

~~~text
src/
├── com.example.model/
│   ├── module-info.java
│   └── com/example/model/CustomerId.java
├── com.example.api/
│   ├── module-info.java
│   └── com/example/api/CustomerService.java
└── com.example.client/
    ├── module-info.java
    └── com/example/client/Main.java
~~~

### 5.1. Mô-đun model

Tệp **src/com.example.model/module-info.java**:

~~~java
module com.example.model {
    exports com.example.model;
}
~~~

Tệp **src/com.example.model/com/example/model/CustomerId.java**:

~~~java
package com.example.model;

public record CustomerId(String value) { }
~~~

Package **com.example.model** được export để mô-đun khác có thể dùng kiểu **CustomerId** theo quy tắc truy cập thông thường.

### 5.2. Mô-đun API

Tệp **src/com.example.api/module-info.java**:

~~~java
module com.example.api {
    requires transitive com.example.model;
    exports com.example.api;
}
~~~

Tệp **src/com.example.api/com/example/api/CustomerService.java**:

~~~java
package com.example.api;

import com.example.model.CustomerId;

public interface CustomerService {
    CustomerId findById(CustomerId id);
}
~~~

Đây là phụ thuộc API thực sự: **CustomerId** xuất hiện cả trong kiểu tham số lẫn kiểu trả về của interface công khai. Vì vậy, mô-đun API khai báo **requires transitive com.example.model**.

### 5.3. Mô-đun client

Tệp **src/com.example.client/module-info.java**:

~~~java
module com.example.client {
    requires com.example.api;
}
~~~

Client không cần khai báo **requires com.example.model** trong ví dụ này, vì **com.example.api** đã truyền khả năng đọc mô-đun model qua **requires transitive**.

Tệp **src/com.example.client/com/example/client/Main.java**:

~~~java
package com.example.client;

import com.example.api.CustomerService;
import com.example.model.CustomerId;

public final class Main {
    public static void main(String[] args) {
        CustomerService service = id -> id;
        CustomerId id = new CustomerId("C-42");
        System.out.println(service.findById(id).value());
    }
}
~~~

Client có thể tham chiếu **CustomerId** dù module descriptor của nó chỉ yêu cầu **com.example.api**. Đó là hiệu quả của quan hệ readability transitive.

### 5.4. Biên dịch và chạy

Yêu cầu JDK 17 trở lên. Chạy lệnh từ thư mục chứa **src**:

~~~bash
javac -d out --module-source-path src -m com.example.model,com.example.api,com.example.client
java --module-path out -m com.example.client/com.example.client.Main
~~~

Kết quả stdout:

~~~text
C-42
~~~

### 5.5. Phân tích API bằng jdeps

Chạy:

~~~bash
jdeps --api-only -verbose:class --module-path out --module com.example.api
~~~

Trong kết quả, phần quan trọng sẽ có dạng:

~~~text
com.example.api -> com.example.model
   com.example.api.CustomerService -> com.example.model.CustomerId com.example.model
~~~

Dòng phụ thuộc giữa **CustomerService** và **CustomerId** cho thấy kiểu từ model xuất hiện trong API của mô-đun API. Đây là bằng chứng trực tiếp để kiểm tra khai báo **requires transitive**.

Tiếp theo:

~~~bash
jdeps --check com.example.api --module-path out
~~~

Kiểm tra phần **Module descriptor**, **Suggested module descriptor** và **Transitive reduced graph**. Với ví dụ này, descriptor đề xuất vẫn thể hiện:

~~~java
requires transitive com.example.model;
~~~

Như vậy, kết quả phân tích bytecode, descriptor và phép thử client đều thống nhất: model là một phụ thuộc API cần truyền tiếp.

## 6. Trường hợp đối lập: phụ thuộc chỉ dùng trong triển khai

Giả sử một mô-đun service sử dụng mô-đun audit để ghi log, nhưng API công khai không nhận, trả về hoặc kế thừa bất kỳ kiểu nào của audit.

~~~java
module com.example.service {
    requires com.example.audit;
    exports com.example.service.api;
}
~~~

Ví dụ interface công khai chỉ sử dụng kiểu của chính service:

~~~java
package com.example.service.api;

public interface OrderService {
    String findOrderNumber(String orderId);
}
~~~

Lớp triển khai có thể gọi **AuditLogger** trong phần thân phương thức, nhưng client không cần biết kiểu đó để gọi **OrderService**.

Trong trường hợp này:

- **com.example.service** cần **requires com.example.audit** để biên dịch và chạy phần triển khai.
- Client chỉ cần **requires com.example.service**.
- Không nên thêm **requires transitive com.example.audit** nếu không có lý do API nào khác.

Nếu sau này một phương thức công khai được đổi thành trả về **AuditRecord** hoặc nhận **AuditContext**, phụ thuộc audit đã trở thành một phần của chữ ký API. Khi đó cần đánh giá lại descriptor và khả năng tương thích của client.

## 7. Giới hạn của công cụ và các lỗi thường gặp

### 7.1. Xem mọi import là phụ thuộc API

Import có thể chỉ được dùng trong phương thức private hoặc trong phần thân triển khai. Hãy kiểm tra vị trí sử dụng thực tế và chữ ký API thay vì chuyển mọi import thành **requires transitive**.

### 7.2. Dùng jdeps --api-only như một quyết định tự động

**jdeps --api-only** cho biết phụ thuộc từ chữ ký public/protected của các lớp public. Công cụ không hiểu toàn bộ ý đồ thiết kế API và không thể tự quyết định mô-đun nào nên được công khai như một hợp đồng ổn định.

Hãy đối chiếu kết quả với package được export và module descriptor. Đặc biệt, kiểm tra các phụ thuộc qua reflection, tên lớp dạng chuỗi, cấu hình tài nguyên hoặc cơ chế nạp lớp động riêng; những quan hệ này không nhất thiết xuất hiện như phụ thuộc kiểu thông thường trong chữ ký bytecode.

### 7.3. Nhầm requires transitive với exports

**requires transitive B** truyền khả năng đọc B cho client của A. Nó không export package của B. Nếu package chứa kiểu B không được export, client vẫn không thể dùng kiểu đó theo cách truy cập thông thường.

### 7.4. Bỏ qua client kiểm chứng

Một descriptor có thể biên dịch được bên trong mô-đun nhưng vẫn chưa phù hợp với cách client sử dụng API. Hãy thử một client tối thiểu chỉ khai báo **requires A**. Nếu client cần kiểu B từ API của A mà không đọc được B, hãy xem lại quan hệ transitive hoặc thiết kế API.

### 7.5. Phân tích nhầm artifact

Chạy **jdeps** trên đúng output được tạo từ phiên bản mã nguồn và descriptor dự định phát hành. Nếu phân tích JAR cũ hoặc output chưa được build lại, kết quả có thể không phản ánh API hiện tại.

### 7.6. Truyền tiếp quá nhiều phụ thuộc

**requires transitive** làm tăng phạm vi module graph mà client có thể đọc và gắn client chặt hơn với các kiểu của mô-đun phụ thuộc. Nếu muốn giữ phụ thuộc ở mức triển khai, hãy dùng **requires** và cân nhắc thiết kế API bằng interface, DTO hoặc abstraction thuộc mô-đun của mình.

## 8. Checklist trước khi quyết định requires transitive

- Xác định đúng mô-đun và package đang export.
- Kiểm tra kiểu của trường, tham số, giá trị trả về, ngoại lệ, superclass, interface và generic type trong API public/protected.
- Phân biệt kiểu xuất hiện trong chữ ký API với kiểu chỉ được dùng trong phần thân triển khai.
- Chạy **jdeps --api-only -verbose:class** trên artifact vừa build.
- Dùng **jdeps --check** để kiểm tra descriptor và module graph.
- Đảm bảo package chứa kiểu phụ thuộc được mô-đun sở hữu export nếu client cần truy cập thông thường.
- Thử biên dịch client chỉ yêu cầu mô-đun API.
- Chỉ dùng **requires transitive** khi việc truyền khả năng đọc phản ánh đúng hợp đồng API mà client cần sử dụng.
- Giữ **requires** thông thường cho phụ thuộc triển khai không cần lộ ra bên ngoài.

Nguyên tắc cốt lõi: **hãy để module descriptor phản ánh API thực sự, không phản ánh mọi chi tiết triển khai**. Kết hợp rà soát chữ ký, **jdeps --api-only**, **jdeps --check** và một client kiểm chứng sẽ giúp xác định chính xác phụ thuộc nào cần truyền tiếp trong JPMS.