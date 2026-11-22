# Chọn ranh giới mô-đun theo trách nhiệm và hợp đồng công khai

Trong JPMS, một mô-đun tốt gom những thành phần cùng phục vụ một trách nhiệm, công bố đúng hợp đồng mà phần khác cần sử dụng và giữ chi tiết triển khai ở bên trong. Ranh giới này quyết định module nào sở hữu chức năng nào, module khác được phép phụ thuộc vào phần nào và thay đổi nội bộ có thể lan đến đâu.

Mục tiêu không phải tạo thật nhiều module. Mục tiêu là làm cho cấu trúc phụ thuộc phản ánh kiến trúc của hệ thống, để mỗi phần có trách nhiệm rõ, API có thể duy trì và thay đổi được kiểm soát.

Phạm vi bài học dùng JPMS hiện hành và ví dụ có thể biên dịch bằng Java 17 trở lên. Các module trong ví dụ chạy trong cùng một JVM.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định trách nhiệm và ranh giới hợp lý cho từng module.
- Phân biệt API công khai với package và class triển khai nội bộ.
- Thiết kế hướng phụ thuộc không tạo vòng và không làm lộ chi tiết không cần thiết.
- Chọn khi nào dùng module API, module triển khai hoặc service provider.
- Đọc module descriptor và hiểu cách `requires`, `exports`, `uses`, `provides` hỗ trợ ranh giới.
- Đánh giá ranh giới module bằng các tiêu chí cohesion, coupling, quyền sở hữu dữ liệu và khả năng thay đổi.

## 1. Ranh giới mô-đun là gì?

Một module là một đơn vị có tên, có thể khai báo dependency và xác định package nào được công bố. Trong JPMS, module descriptor `module-info.java` mô tả các quan hệ đó.

Ranh giới module có hai mặt:

1. **Ranh giới trách nhiệm:** module chịu trách nhiệm cho một nhóm chức năng có ý nghĩa. Các thành phần bên trong thường thay đổi cùng nhau vì phục vụ cùng một mục đích.
2. **Ranh giới truy cập:** module công bố một hợp đồng đủ dùng cho module khác; phần còn lại được giữ nội bộ.

Một module có thể chứa nhiều package và nhiều class. Package giúp tổ chức namespace và phạm vi truy cập trong mã nguồn; module bổ sung ranh giới ở cấp cao hơn, giữa các nhóm package. Chỉ tạo thư mục hoặc package mới chưa tạo ra ranh giới JPMS.

### 1.1. Trách nhiệm phải có ý nghĩa nghiệp vụ hoặc kỹ thuật rõ ràng

Ví dụ, trong hệ thống bán hàng, các trách nhiệm có thể gồm:

- Catalog: quản lý thông tin sản phẩm và khả năng tra cứu.
- Ordering: tiếp nhận và quản lý đơn hàng.
- Billing: tính tiền và xử lý hóa đơn.
- Identity: xác thực và thông tin định danh.

Đây là các năng lực khác nhau, có quy tắc và lý do thay đổi khác nhau. Chúng có thể là ứng viên module nếu có API và dependency đủ rõ.

Một module không nhất thiết tương ứng với một màn hình, một controller, một bảng database hoặc một class. Những cách chia đó thường phản ánh chi tiết triển khai hơn là trách nhiệm ổn định.

### 1.2. Cohesion và coupling

Hai khái niệm giúp đánh giá ranh giới:

- **Cohesion (tính gắn kết):** các thành phần trong cùng module có liên quan chặt chẽ đến một trách nhiệm hay không.
- **Coupling (mức phụ thuộc):** một module cần biết bao nhiêu chi tiết của module khác để hoàn thành công việc.

Ranh giới tốt thường có cohesion cao bên trong và coupling thấp ở bên ngoài. Nếu một thay đổi nghiệp vụ thường xuyên buộc nhiều module cùng sửa, có thể trách nhiệm đang bị chia sai hoặc hợp đồng công khai chưa phù hợp.

Ví dụ, logic tính giá và chính sách giảm giá thường thuộc cùng một năng lực pricing. Nếu đặt chúng ở nhiều module không có hợp đồng rõ, các module có thể phải truy cập trực tiếp vào dữ liệu và quy tắc nội bộ của nhau.

### 1.3. Ranh giới dựa trên lý do thay đổi

Hãy xem xét các thay đổi thường xảy ra:

- Quy tắc nào thường thay đổi cùng nhau?
- Phần nào có vòng đời phát triển riêng?
- Phần nào cần được kiểm thử và phát hành cùng nhau?
- Nhóm nào chịu trách nhiệm duy trì hợp đồng?
- Thành phần nào có thể thay thế mà không buộc phần gọi sửa?

Các class thường thay đổi cùng nhau có thể thuộc cùng một module. Các phần có lý do thay đổi độc lập có thể là ứng viên tách riêng, nếu việc tách không tạo ra quá nhiều giao tiếp và dependency.

Không nên quyết định chỉ dựa trên số dòng mã hoặc số class. Module lớn vẫn có thể hợp lý nếu trách nhiệm thống nhất; module nhỏ vẫn có thể không hợp lý nếu nó chỉ tách một class mà không tạo ra hợp đồng có giá trị.

## 2. Thiết kế hợp đồng công khai

### 2.1. Hợp đồng là phần module cam kết cung cấp

Hợp đồng công khai là những kiểu, phương thức và quy tắc sử dụng mà module cho phép bên ngoài dựa vào. Trong JPMS, package phải được export thì kiểu public trong package đó mới có thể được module khác truy cập theo cách thông thường.

Một hợp đồng tốt cần:

- Thể hiện đúng năng lực module cung cấp.
- Có tên và kiểu dữ liệu dễ hiểu.
- Chỉ công bố các thao tác mà bên gọi thực sự cần.
- Không buộc bên gọi biết cách lưu trữ hoặc xử lý nội bộ.
- Có thể duy trì khi module thay đổi triển khai.
- Có quy tắc lỗi và ý nghĩa dữ liệu rõ ràng.

Ví dụ, module catalog có thể công bố `ProductCatalog` với thao tác tìm sản phẩm. Bên gọi cần biết cách tìm và nhận kết quả; bên gọi không cần biết dữ liệu được lấy từ bộ nhớ, database hay dịch vụ khác.

### 2.2. Công bố interface hoặc kiểu API phù hợp

Interface có ích khi module muốn xác định một hợp đồng có thể có nhiều triển khai. Record hoặc class bất biến có ích khi cần truyền dữ liệu qua ranh giới.

Ví dụ:

~~~java
package com.acme.catalog.api;

import java.util.List;

public interface ProductCatalog {
    List<Product> findAll();

    String sourceName();
}
~~~

~~~java
package com.acme.catalog.api;

public record Product(String id, String name, int price) { }
~~~

Module khác phụ thuộc vào kiểu trong package API. Việc triển khai interface có thể thay đổi mà bên gọi vẫn giữ nguyên cách sử dụng nếu hợp đồng không đổi.

Không phải API nào cũng cần interface. Nếu chỉ có một cách thực hiện ổn định và không có nhu cầu thay thế hoặc mở rộng, một class công khai có thể đơn giản hơn. Tạo interface cho mọi class sẽ làm hợp đồng phình to và tăng số kiểu phải duy trì.

### 2.3. Giữ chi tiết triển khai ở package không export

Một module có thể chứa package API và nhiều package nội bộ:

~~~text
catalog.module
├── com.acme.catalog.api       # được export
├── com.acme.catalog.internal  # nội bộ
├── com.acme.catalog.storage   # nội bộ
└── com.acme.catalog.mapping   # nội bộ
~~~

Module khác chỉ truy cập các package được export. Những package còn lại có thể chứa repository, adapter, mapper, cache, thuật toán và helper riêng.

Đừng export toàn bộ package chỉ để tiện gọi. Mỗi package được export mở rộng bề mặt API và có thể trở thành cam kết mà module phải duy trì. Hãy thêm export khi có một nhu cầu sử dụng bên ngoài rõ ràng.

### 2.4. Phân biệt exports và opens

- `exports` cho phép module khác truy cập các kiểu public trong package được công bố.
- `opens` cho phép truy cập phản chiếu sâu vào package theo quy tắc JPMS; nó không thay thế hợp đồng API thông thường.

Chỉ mở package khi có nhu cầu phản chiếu cụ thể, chẳng hạn một thành phần cần đọc hoặc tạo đối tượng qua reflection. Nếu module cần mở cho một module xác định, có thể dùng qualified opens thay vì mở cho tất cả. Không dùng `opens` để thay cho thiết kế API công khai.

### 2.5. Tránh để API rò rỉ chi tiết nội bộ

Một API sẽ khó thay đổi nếu kiểu trả về hoặc tham số của nó phụ thuộc trực tiếp vào triển khai bên trong. Ví dụ, nếu module catalog trả về class `InternalDatabaseRow`, mọi module gọi sẽ bị ràng buộc vào cấu trúc database.

Hãy dùng kiểu thuộc hợp đồng công khai như `Product`, `ProductSummary` hoặc interface nghiệp vụ. Không đưa connection, entity nội bộ, class cache hoặc kiểu riêng của thư viện triển khai ra ngoài nếu bên gọi không thực sự cần chúng.

Cũng cần tránh tạo một module `common` hoặc `shared` chứa mọi kiểu dùng chung. Một module dùng chung quá lớn dễ trở thành nơi tập trung dependency và khiến mọi module phụ thuộc vào nhau. Chỉ đưa vào API chung những kiểu có ý nghĩa ổn định và thật sự thuộc hợp đồng giữa các bên.

## 3. Thiết kế hướng phụ thuộc

### 3.1. Module sử dụng phụ thuộc vào hợp đồng

Một hướng thiết kế phổ biến là:

~~~text
Ứng dụng / module điều phối
          |
          v
       API module
          ^
          |
Module triển khai
~~~

Module triển khai phụ thuộc vào API để thực hiện hợp đồng. Module sử dụng cũng phụ thuộc vào API. Nhờ vậy, module sử dụng không cần phụ thuộc vào class triển khai cụ thể.

Đây là một cách áp dụng nguyên tắc phụ thuộc vào abstraction. JPMS không tự thiết kế đồ thị đúng thay cho bạn; module descriptor chỉ khai báo và giúp JVM/trình biên dịch thực thi các quan hệ đã chọn.

### 3.2. Tránh dependency vòng

Nếu A cần B và B lại cần A, hai module bị gắn chặt. Việc biên dịch, kiểm thử và thay đổi riêng từng module trở nên khó khăn; trách nhiệm có thể đã được chia chưa đúng.

Khi thấy dependency vòng:

1. Xác định phần hợp đồng thực sự được dùng chung.
2. Đưa hợp đồng đó vào một module API có trách nhiệm rõ.
3. Cho các module cần dùng phụ thuộc vào API.
4. Đưa phần điều phối lên module cấp cao hơn nếu quan hệ giữa hai bên là một quy trình.
5. Nếu hai phần luôn thay đổi và phát hành cùng nhau, cân nhắc giữ chúng trong cùng một module.

Không tạo module API rỗng chỉ để phá vòng dependency. Module mới phải có một hợp đồng có ý nghĩa và một lý do tồn tại.

### 3.3. Hạn chế phụ thuộc ngược từ tầng thấp lên tầng cao

Ví dụ, module storage không nên phụ thuộc vào module app chỉ để gọi một callback hoặc lấy cấu hình. Hãy xác định hợp đồng mà storage cần và đặt nó ở vị trí phù hợp trong đồ thị kiến trúc.

Nếu module thấp tầng biết quá nhiều về ứng dụng, nó khó tái sử dụng và khó kiểm thử độc lập. Module cấp cao nên chịu trách nhiệm điều phối các năng lực, còn module cung cấp năng lực giữ quy tắc và dữ liệu thuộc trách nhiệm của mình.

### 3.4. Không tạo split package

Split package xảy ra khi cùng một package name xuất hiện trong nhiều module. Đây là nguồn gây mơ hồ và xung đột khi sử dụng module path. Mỗi package nên có một chủ sở hữu rõ ràng.

Khi tách một package hiện có thành module, cần xác định module nào sở hữu package đó và di chuyển các class liên quan cùng nhau. Không chia một package thành nhiều module rồi trông đợi JPMS hợp nhất chúng.

### 3.5. Dùng requires transitive có chủ đích

Thông thường, `requires` khai báo dependency trực tiếp của module. `requires transitive` còn cho phép module đọc một dependency được truyền tiếp đến module phụ thuộc vào nó.

Chỉ dùng `requires transitive` khi kiểu trong API công khai của module buộc bên sử dụng cũng phải đọc module dependency đó. Nếu chỉ dùng dependency trong triển khai nội bộ, `requires` là đủ. Dùng transitive tùy tiện sẽ làm lộ dependency và mở rộng đồ thị mà bên sử dụng phải mang theo.

## 4. Khi nào nên tạo API module và module triển khai riêng?

Tách API và triển khai thành các module riêng có ích khi:

- Nhiều ứng dụng cần dùng chung một hợp đồng.
- Có nhiều cách triển khai hợp lệ, ví dụ in-memory, file hoặc remote.
- Muốn bên sử dụng không phụ thuộc vào package triển khai.
- Cần thay provider theo môi trường hoặc cấu hình.
- API cần được duy trì ổn định hơn tốc độ thay đổi của triển khai.

Không cần tách nếu API và triển khai luôn được sử dụng cùng nhau, không có bên dùng độc lập và việc tách chỉ tạo thêm module rỗng. Có thể giữ package API và package nội bộ trong cùng một module; JPMS vẫn kiểm soát được package nào được export.

### 4.1. ServiceLoader cho điểm mở rộng

Khi module sử dụng chỉ cần một hợp đồng và không cần biết class triển khai cụ thể, có thể dùng `ServiceLoader`:

- API module khai báo interface dịch vụ.
- Module triển khai cung cấp implementation.
- Module ứng dụng khai báo `uses`.
- Module provider khai báo `provides ... with ...`.

Cách này giảm phụ thuộc trực tiếp từ ứng dụng đến class triển khai. Nó hữu ích cho plugin nội bộ, adapter hoặc nhiều provider. Nếu chỉ có một implementation cố định và không cần khả năng thay thế, gọi trực tiếp API có thể đơn giản hơn.

## 5. Ví dụ chạy được: tách hợp đồng catalog khỏi triển khai

Ví dụ gồm ba module:

- `catalog.api`: sở hữu hợp đồng `ProductCatalog` và kiểu dữ liệu `Product`.
- `catalog.memory`: triển khai hợp đồng bằng dữ liệu trong bộ nhớ; package triển khai không export.
- `catalog.app`: sử dụng hợp đồng thông qua `ServiceLoader`, không import class triển khai.

Cấu trúc thư mục:

~~~text
src/
├── catalog.api/
│   ├── module-info.java
│   └── com/acme/catalog/api/
│       ├── Product.java
│       └── ProductCatalog.java
├── catalog.memory/
│   ├── module-info.java
│   └── com/acme/catalog/memory/
│       └── InMemoryProductCatalog.java
└── catalog.app/
    ├── module-info.java
    └── com/acme/catalog/app/
        └── Main.java
~~~

### 5.1. Module catalog.api

File `src/catalog.api/module-info.java`:

~~~java
module catalog.api {
    exports com.acme.catalog.api;
}
~~~

File `src/catalog.api/com/acme/catalog/api/Product.java`:

~~~java
package com.acme.catalog.api;

public record Product(String id, String name, int price) { }
~~~

File `src/catalog.api/com/acme/catalog/api/ProductCatalog.java`:

~~~java
package com.acme.catalog.api;

import java.util.List;

public interface ProductCatalog {
    List<Product> findAll();

    String sourceName();
}
~~~

Module này công bố đúng một package API. Bên sử dụng biết Product và ProductCatalog; nó không biết dữ liệu được lưu ở đâu.

### 5.2. Module catalog.memory

File `src/catalog.memory/module-info.java`:

~~~java
module catalog.memory {
    requires catalog.api;

    provides com.acme.catalog.api.ProductCatalog
            with com.acme.catalog.memory.InMemoryProductCatalog;
}
~~~

File `src/catalog.memory/com/acme/catalog/memory/InMemoryProductCatalog.java`:

~~~java
package com.acme.catalog.memory;

import com.acme.catalog.api.Product;
import com.acme.catalog.api.ProductCatalog;
import java.util.List;

public final class InMemoryProductCatalog implements ProductCatalog {
    public InMemoryProductCatalog() {
    }

    @Override
    public List<Product> findAll() {
        return List.of(
                new Product("P-100", "Keyboard", 120),
                new Product("P-200", "Mouse", 40)
        );
    }

    @Override
    public String sourceName() {
        return "in-memory";
    }
}
~~~

Module triển khai khai báo `requires catalog.api` vì nó thực hiện hợp đồng. Nó khai báo provider bằng `provides`. Package `com.acme.catalog.memory` không được export nên ứng dụng không thể truy cập implementation theo cách thông thường.

### 5.3. Module catalog.app

File `src/catalog.app/module-info.java`:

~~~java
module catalog.app {
    requires catalog.api;

    uses com.acme.catalog.api.ProductCatalog;
}
~~~

File `src/catalog.app/com/acme/catalog/app/Main.java`:

~~~java
package com.acme.catalog.app;

import com.acme.catalog.api.Product;
import com.acme.catalog.api.ProductCatalog;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ProductCatalog catalog = ServiceLoader
                .load(ProductCatalog.class)
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("No ProductCatalog provider"));

        List<Product> products = catalog.findAll();

        System.out.println("catalog=" + catalog.sourceName());
        System.out.println("count=" + products.size());
        System.out.println("products="
                + products.stream().map(Product::name).toList());
    }
}
~~~

Ứng dụng chỉ phụ thuộc vào API. Nó không import hoặc tạo `InMemoryProductCatalog`. Provider được tìm thông qua hợp đồng dịch vụ.

### 5.4. Biên dịch và chạy bằng Java 17+

Từ thư mục chứa `src`, chạy:

~~~bash
javac --release 17 --module-source-path src -d out -m catalog.api,catalog.memory,catalog.app
java --module-path out -m catalog.app/com.acme.catalog.app.Main
~~~

Kết quả stdout:

~~~text
catalog=in-memory
count=2
products=[Keyboard, Mouse]
~~~

Ví dụ chứng minh:

1. Hợp đồng API có module riêng và chỉ export package cần thiết.
2. Module triển khai phụ thuộc vào API, nhưng ứng dụng không phụ thuộc vào package triển khai.
3. Ứng dụng yêu cầu service contract; provider đăng ký implementation qua module descriptor.
4. Có thể thay provider bằng một module khác thực hiện cùng hợp đồng mà không phải sửa mã gọi, miễn là hành vi và hợp đồng được giữ tương thích.

Nếu ứng dụng chỉ có một implementation cố định và không cần cơ chế provider, có thể đơn giản hóa bằng cách đặt API và implementation trong cùng module hoặc gọi implementation qua một factory được export. Hãy chọn mức tách phù hợp với nhu cầu thật.

## 6. Quy trình chọn ranh giới module trong dự án

### Bước 1: Liệt kê năng lực và trách nhiệm

Ghi lại các use case, quy tắc nghiệp vụ và thành phần chính. Gom các thành phần cùng phục vụ một năng lực; đánh dấu phần chỉ là tiện ích kỹ thuật dùng chung.

Không bắt đầu bằng cách tạo module cho từng package hiện tại. Cấu trúc package có thể phản ánh lịch sử phát triển chứ chưa chắc phản ánh ranh giới tốt.

### Bước 2: Xác định quyền sở hữu

Với mỗi nhóm chức năng, xác định:

- Ai sở hữu quy tắc và dữ liệu?
- Ai được phép thay đổi trạng thái?
- Module khác cần gọi thao tác nào?
- Thành phần nào chỉ là chi tiết triển khai?
- Phần nào có thể thay đổi độc lập?

Một module nên có quyền sở hữu rõ đối với trách nhiệm của mình. Nếu nhiều module cùng sửa trực tiếp một trạng thái hoặc cùng giữ một bản sao quy tắc, cần xem lại ranh giới.

### Bước 3: Viết hợp đồng trước khi công bố package

Xác định các kiểu dữ liệu, interface và thao tác mà bên ngoài thực sự cần. Kiểm tra xem API có làm lộ class triển khai, kiểu database hoặc dependency không cần thiết hay không.

Hãy xem hợp đồng từ góc nhìn của người sử dụng: họ cần hoàn thành use case nào, cần dữ liệu nào và cần xử lý lỗi ra sao? Không công bố method chỉ vì class triển khai đang có method đó.

### Bước 4: Vẽ đồ thị phụ thuộc

Vẽ module nào cần API của module nào. Hướng phụ thuộc nên dễ giải thích, không có vòng và không kéo dependency triển khai lên module ứng dụng một cách không cần thiết.

Kiểm tra các trường hợp:
- Module chỉ dùng một kiểu API nhưng phải phụ thuộc cả module triển khai.
- Module thấp tầng phải biết module ứng dụng.
- Nhiều module phụ thuộc vào một module common quá lớn.
- Cùng một package xuất hiện ở nhiều module.
- API công khai làm lộ một dependency cần `requires transitive` nhưng descriptor chưa khai báo đúng.

### Bước 5: Giữ package nội bộ và giới hạn export

Đưa class triển khai vào package nội bộ. Chỉ export package hợp đồng. Chỉ mở package cho reflection khi có yêu cầu cụ thể và có thể xác định module được phép truy cập.

### Bước 6: Kiểm chứng bằng thay đổi thật

Thử thay implementation mà không sửa module gọi. Thử thêm một module provider mới nếu kiến trúc cần mở rộng. Kiểm tra rằng thay đổi nội bộ không buộc bên sử dụng truy cập package nội bộ.

Một ranh giới chỉ có ý nghĩa khi nó giảm sự phụ thuộc trong các thay đổi thật, không chỉ làm module descriptor trông gọn.

### Bước 7: Đưa quy tắc vào review

Khi review thay đổi, kiểm tra:

- Module có đang nhận thêm trách nhiệm không liên quan?
- API có công bố kiểu nội bộ không?
- Dependency mới có đi đúng hướng không?
- Có dependency vòng hoặc split package không?
- Có thể giữ thay đổi bên trong module không?
- Tên module, package và API có diễn tả đúng trách nhiệm không?

## 7. Các dấu hiệu ranh giới đang được chọn sai

| Dấu hiệu | Vấn đề có thể có | Hướng xử lý |
| --- | --- | --- |
| Mỗi thay đổi nhỏ phải sửa nhiều module | Trách nhiệm bị chia vụn hoặc API không phù hợp | Gom phần thường thay đổi cùng nhau hoặc thiết kế lại hợp đồng |
| Module export gần như mọi package | Rò rỉ chi tiết triển khai | Giữ package nội bộ và thu nhỏ API |
| Module ứng dụng import class triển khai cụ thể | Phụ thuộc vào implementation | Phụ thuộc API hoặc dùng service provider khi cần |
| Có dependency vòng | Hướng trách nhiệm chưa rõ | Tách hợp đồng có ý nghĩa hoặc đặt điều phối ở tầng phù hợp |
| Module common chứa nhiều quy tắc nghiệp vụ | Trách nhiệm sở hữu bị mờ | Chuyển quy tắc về module nghiệp vụ sở hữu nó |
| Module chỉ có một class và không có ranh giới hữu ích | Tách quá nhỏ | Cân nhắc gộp vào module có cùng trách nhiệm |
| Nhiều module cùng sửa một trạng thái | Quyền sở hữu dữ liệu không rõ | Chọn một module sở hữu thao tác thay đổi và công bố API |

## 8. Checklist tự đánh giá

- [ ] Giải thích được ranh giới trách nhiệm khác với ranh giới package như thế nào.
- [ ] Đánh giá được cohesion và coupling khi quyết định tách module.
- [ ] Xác định được các thành phần thường thay đổi cùng nhau.
- [ ] Nêu được hợp đồng công khai và lý do cần giữ nó nhỏ.
- [ ] Phân biệt `exports` với `opens`.
- [ ] Biết vì sao không nên export package triển khai.
- [ ] Thiết kế được hướng phụ thuộc từ module sử dụng đến API.
- [ ] Nhận diện dependency vòng và split package.
- [ ] Biết khi nào nên tách API và implementation.
- [ ] Đọc được ví dụ `uses` và `provides` với ServiceLoader.
- [ ] Biết kiểm chứng ranh giới bằng cách thay implementation mà không sửa bên gọi.
- [ ] Không tạo module chỉ để tăng số lượng hoặc phản ánh máy móc cấu trúc thư mục.
