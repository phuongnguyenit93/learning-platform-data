# requires và cạnh phụ thuộc module

Trong Java Platform Module System (JPMS), một module khai báo dependency bằng chỉ thị `requires` trong file `module-info.java`. Mỗi khai báo tạo một quan hệ phụ thuộc có hướng từ module đang khai báo đến module được yêu cầu. Tập hợp các quan hệ này tạo thành đồ thị phụ thuộc module và được Java dùng khi biên dịch, giải quyết module và chạy ứng dụng.

Hiểu đúng `requires` giúp bạn biết module nào cần có mặt, module nào được đọc, vì sao một dependency được truyền đến client, và cách xử lý lỗi khi module descriptor thiếu hoặc khai báo sai phụ thuộc.

## Mục tiêu

Sau bài học, bạn có thể:

- Viết và đọc chỉ thị `requires` trong `module-info.java`.
- Giải thích hướng của cạnh phụ thuộc giữa module sử dụng và module được yêu cầu.
- Phân biệt `requires`, `requires transitive` và `requires static`.
- Hiểu vai trò của dependency trong quá trình module resolution.
- Phân biệt việc module đọc được một module với việc package của module đó được export.
- Biên dịch và chạy ví dụ gồm hai named module có quan hệ phụ thuộc trực tiếp.

## 1. Cú pháp của requires

Chỉ thị `requires` được đặt bên trong module declaration:

~~~java
module com.acme.application {
    requires com.acme.logging;
}
~~~

Trong ví dụ này, `com.acme.application` là module khai báo dependency, còn `com.acme.logging` là module được yêu cầu.

Cú pháp tổng quát:

~~~java
requires [static] [transitive] module.name;
~~~

Hai modifier `static` và `transitive` là tùy chọn. Chúng có thể được dùng riêng hoặc kết hợp để xác định cách dependency được xử lý và truyền tới module phụ thuộc.

Một số quy tắc cơ bản:

- Tên sau `requires` là tên module, không phải tên package hay tên file JAR.
- Module được yêu cầu phải có thể được tìm thấy trong cấu hình module tương ứng, thường qua module path.
- Một module không thể khai báo `requires` chính nó.
- Một module chỉ nên khai báo một quan hệ requires cho mỗi tên module.
- Quan hệ phụ thuộc giữa các named module phải tạo thành đồ thị không có chu trình.
- Mỗi named module, ngoại trừ `java.base`, mặc định đọc `java.base`; vì vậy thường không cần ghi `requires java.base;`.

Tên module có phân biệt chữ hoa và chữ thường. Tên được dùng trong `requires` phải khớp với tên module đã được khai báo hoặc tên module mà Java xác định cho dependency đó.

## 2. Cạnh phụ thuộc có hướng

Giả sử module A sử dụng API do module B cung cấp và khai báo:

~~~java
module A {
    requires B;
}
~~~

Ta có thể biểu diễn quan hệ này như sau:

~~~text
A  ──requires──>  B
    module A đọc B
~~~

Trong bài học này, mũi tên đi từ module phụ thuộc đến module được yêu cầu:

- A là module phụ thuộc.
- B là dependency của A.
- A có quan hệ đọc trực tiếp với B.
- B không cần khai báo `requires A;` chỉ vì A phụ thuộc vào B.

Đây là quan hệ có hướng. Nếu A yêu cầu B, điều đó không có nghĩa B cũng tự động đọc A.

Khi có nhiều module:

~~~text
com.acme.app ──requires──> com.acme.service
com.acme.app ──requires──> com.acme.logging
com.acme.service ────────> com.acme.model
~~~

Đồ thị cho biết app phụ thuộc trực tiếp vào service và logging; service phụ thuộc vào model. Mỗi module khai báo dependency của chính nó trong module descriptor của mình.

### 2.1. requires trực tiếp không tự truyền khả năng đọc

Giả sử có ba module:

~~~text
A ──requires──> B ──requires──> C
~~~

Module B khai báo `requires C;`, còn A chỉ khai báo `requires B;`.

Khi đó:

- B đọc C vì B khai báo dependency trực tiếp.
- A đọc B vì A khai báo dependency trực tiếp.
- A không tự động đọc C chỉ vì B đọc C.

Nếu mã nguồn A cần tham chiếu kiểu thuộc C, A phải khai báo `requires C;` hoặc B phải công bố dependency C bằng `requires transitive C;`.

Điểm này phân biệt **đồ thị dependency** với **tập module mà một module được phép đọc**. Module resolution có thể cần tìm và đưa C vào cấu hình vì B phụ thuộc C, nhưng việc đó không tự tạo quan hệ đọc từ A đến C.

## 3. requires transitive: truyền dependency đến client

Một module có thể dùng kiểu của dependency trong API public. Khi các module khác phụ thuộc vào API đó, chúng thường cũng cần đọc module chứa kiểu được công bố.

Ví dụ:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

Module service đọc model và khai báo quan hệ đó là transitive. Module nào đọc service cũng được hưởng quan hệ đọc tới model.

Đồ thị:

~~~text
com.acme.app ──requires──> com.acme.service
                                  |
                                  └──requires transitive──> com.acme.model
~~~

Module app chỉ cần:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

App có thể đọc cả service và model. Điều này hữu ích khi API public của service sử dụng kiểu thuộc model, chẳng hạn kiểu tham số, kiểu trả về, kiểu generic hoặc interface cha.

Không nên dùng `requires transitive` cho mọi dependency. Nếu dependency chỉ phục vụ triển khai nội bộ và không cần được client đọc, dùng `requires` thông thường sẽ giữ đồ thị phụ thuộc gọn hơn.

## 4. requires static: dependency tùy chọn lúc chạy

Modifier `static` dùng để khai báo dependency bắt buộc trong quá trình biên dịch nhưng có thể không cần hiện diện khi chạy:

~~~java
module com.acme.tool {
    requires static com.acme.annotations;
}
~~~

Cách khai báo này thường phù hợp với dependency chỉ phục vụ compile time, ví dụ một thư viện annotation mà ứng dụng không cần sử dụng khi runtime.

Cần phân biệt:

- Khi biên dịch, module được khai báo bằng `requires static` vẫn phải được tìm thấy để compiler kiểm tra dependency.
- Khi chạy, dependency đó có thể vắng mặt mà không bị yêu cầu như một dependency runtime bắt buộc.
- Nếu code thực thi vẫn cố nạp hoặc sử dụng class từ dependency đã vắng mặt, ứng dụng có thể gặp lỗi nạp class hoặc liên kết.
- `requires static` không có nghĩa là package của dependency được export.

Nếu cần kết hợp cả hai hành vi, module có thể khai báo dependency static và transitive:

~~~java
module com.acme.api {
    requires static transitive com.acme.annotations;
}
~~~

Hãy dùng kết hợp này khi dependency vừa cần được truyền trong quan hệ đọc ở giai đoạn biên dịch vừa có thể không cần ở runtime. Xem xét cách client sử dụng API để bảo đảm việc thiếu dependency lúc chạy là hợp lệ.

## 5. Module resolution sử dụng requires như thế nào?

Khi biên dịch hoặc chạy một ứng dụng modular, Java cần xác định tập module tạo thành cấu hình ứng dụng. Quá trình này thường được gọi là **module resolution**.

Ở mức khái quát, Java thực hiện các việc sau:

1. Xác định module gốc cần biên dịch hoặc chạy.
2. Tìm các module được yêu cầu trực tiếp trong module descriptor.
3. Tìm tiếp các dependency của những module vừa được tìm thấy.
4. Kiểm tra tên module, khả năng quan sát và tính hợp lệ của các quan hệ phụ thuộc.
5. Xây dựng cấu hình module để biên dịch hoặc chạy.

Ví dụ, nếu app yêu cầu service và service yêu cầu model:

~~~text
Root module: app
       |
       v
     service
       |
       v
      model
~~~

Java cần giải quyết cả service và model để tạo cấu hình chạy hợp lệ. Tuy nhiên, việc model được giải quyết vào cấu hình không đồng nghĩa app luôn được phép đọc model; cần xem modifier của quan hệ requires giữa service và model.

### 5.1. Module path cung cấp nơi tìm module

Ví dụ biên dịch ứng dụng modular:

~~~bash
javac --module-path libs -d out --module-source-path src -m com.acme.app
~~~

Ví dụ chạy:

~~~bash
java --module-path "out;libs" -m com.acme.app/com.acme.app.Main
~~~

Trong lệnh chạy trên, dấu chấm phẩy là dấu phân cách module path trên Windows. Trên Linux và macOS, dùng dấu hai chấm:

~~~bash
java --module-path "out:libs" -m com.acme.app/com.acme.app.Main
~~~

Module path cho Java biết nơi tìm các module có thể quan sát. Chỉ thị `requires` cho biết module nào cần dependency nào. Hai phần này phối hợp với nhau trong quá trình resolution.

Đặt một JAR vào thư mục `libs` không tự tạo ra quan hệ phụ thuộc trong module descriptor. Nếu module app cần module logging, app vẫn phải khai báo `requires com.acme.logging;`.

### 5.2. Quan sát quá trình resolution

Có thể yêu cầu JVM hiển thị thông tin module resolution khi chạy:

~~~bash
java --show-module-resolution --module-path out -m com.acme.app/com.acme.app.Main
~~~

Thông tin hiển thị giúp nhận biết các module gốc và dependency mà JVM đã giải quyết. Đây là công cụ hữu ích khi một module không được tìm thấy hoặc cấu hình module có kết quả khác với dự kiến.

## 6. Ví dụ hoàn chỉnh: app requires service

Ta tạo hai named module:

- `com.acme.service` cung cấp class `GreetingService`.
- `com.acme.app` sử dụng class đó.

Cấu trúc thư mục:

~~~text
src/
├── com.acme.service/
│   ├── module-info.java
│   └── com/acme/service/api/GreetingService.java
└── com.acme.app/
    ├── module-info.java
    └── com/acme/app/Main.java
~~~

### 6.1. Module service

File `src/com.acme.service/module-info.java`:

~~~java
module com.acme.service {
    exports com.acme.service.api;
}
~~~

File `src/com.acme.service/com/acme/service/api/GreetingService.java`:

~~~java
package com.acme.service.api;

public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Service export package `com.acme.service.api` để module khác có thể truy cập API public trong package đó.

### 6.2. Module app

File `src/com.acme.app/module-info.java`:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

File `src/com.acme.app/com/acme/app/Main.java`:

~~~java
package com.acme.app;

import com.acme.service.api.GreetingService;

public class Main {
    public static void main(String[] args) {
        GreetingService service = new GreetingService();
        System.out.println(service.greet("Lan"));
    }
}
~~~

App khai báo `requires com.acme.service;` để đọc module service. Service export package chứa class cần dùng. Hai điều kiện này phối hợp để mã nguồn app có thể import và gọi `GreetingService`.

### 6.3. Biên dịch và chạy

Đứng tại thư mục chứa `src`:

~~~bash
javac --module-source-path src -d out -m com.acme.service,com.acme.app
~~~

Chạy ứng dụng:

~~~bash
java --module-path out -m com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Hello, Lan
~~~

Ví dụ này thể hiện một cạnh dependency trực tiếp từ app đến service. Nếu app bỏ `requires com.acme.service;`, compiler không có quan hệ đọc cần thiết để app tham chiếu API của service.

## 7. requires không thay thế exports

Một nhầm lẫn thường gặp là cho rằng chỉ cần khai báo `requires B;` thì module A có thể sử dụng mọi class của B. Thực tế, hai chỉ thị giải quyết hai việc khác nhau:

| Chỉ thị | Ý nghĩa |
|---|---|
| `requires B;` | Module hiện tại đọc module B và khai báo dependency trực tiếp |
| `exports p;` trong B | Công bố package p cho các module khác đọc B |
| `exports p to A;` trong B | Chỉ công bố package p cho module A |
| `opens p;` trong B | Cho phép deep reflection trên package p lúc chạy |

Ví dụ app đã khai báo:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Nhưng nếu service không export package `com.acme.service.api`, app vẫn không thể import class trong package đó qua API Java thông thường.

Ngược lại, service export package không tự làm app đọc service. App vẫn cần quan hệ `requires` phù hợp.

Ngay cả khi module đọc được và package đã export, class hoặc member còn phải đáp ứng quy tắc truy cập của Java. Một class cấp cao nhất không public không trở thành public chỉ vì package được export.

## 8. Chu trình dependency và cách tổ chức module

Các named module cần có đồ thị dependency không chu trình. Ví dụ sau là thiết kế không hợp lệ:

~~~text
module A requires B
module B requires C
module C requires A
~~~

Một vòng phụ thuộc làm cho các module không thể được giải quyết theo đồ thị module hợp lệ. Compiler hoặc công cụ module sẽ báo lỗi về cyclic dependence.

Khi gặp tình huống này:

1. Xác định module nào đang phụ thuộc vòng lại vào module ban đầu.
2. Tìm phần API chung mà các module đang cần.
3. Cân nhắc tách phần API hoặc abstraction đó sang module riêng.
4. Đảo chiều phụ thuộc thông qua interface hoặc service provider khi phù hợp.
5. Giữ module descriptor thể hiện chiều phụ thuộc rõ ràng.

Ví dụ, nếu A và B cùng cần một abstraction, có thể đưa abstraction vào module C:

~~~text
A ──requires──> C
B ──requires──> C
~~~

Cách này loại bỏ cạnh vòng và giúp các module phụ thuộc vào một hợp đồng chung.

## 9. Các lỗi thường gặp với requires

### Module not found

Java không tìm thấy module được yêu cầu.

Kiểm tra:

- Tên module trong `requires` có chính xác không.
- Module path có chứa thư mục hoặc JAR cung cấp module không.
- JAR có phải là module có tên hợp lệ hoặc automatic module không.
- Module đang biên dịch/chạy có nhận đúng cấu hình module path không.

### Package không hiển thị dù đã requires

Module sử dụng đã đọc module cung cấp nhưng package cần dùng chưa được export, hoặc qualified export không dành cho module hiện tại.

Kiểm tra `exports` trong module descriptor của bên cung cấp.

### Module phụ thuộc gián tiếp nhưng mã nguồn cần kiểu của dependency

Nếu A yêu cầu B, B yêu cầu C bằng `requires` thường, A không tự động đọc C. Thêm `requires C;` ở A hoặc cân nhắc `requires transitive C;` ở B nếu C là một phần của API mà B công bố.

### Dependency chỉ cần lúc biên dịch

Cân nhắc `requires static` nếu dependency không bắt buộc phải hiện diện ở runtime và code runtime có thể hoạt động khi dependency vắng mặt.

### Cyclic dependence

Rà soát lại chiều dependency và tách abstraction chung nếu cần. Không cố giải quyết chu trình bằng cách thêm nhiều chỉ thị `requires` hơn.

## 10. Nguyên tắc khai báo dependency

- Khai báo dependency trực tiếp trong module thực sự sử dụng nó.
- Giữ cạnh phụ thuộc một chiều và tránh chu trình.
- Dùng `requires transitive` khi client của module cần đọc dependency như một phần hợp đồng API.
- Dùng `requires static` khi dependency chỉ bắt buộc ở compile time và có thể vắng mặt lúc chạy.
- Không khai báo transitive chỉ để làm cho lỗi biên dịch biến mất; hãy xác định dependency có thực sự thuộc API public không.
- Kết hợp `requires` với `exports`: một bên xác định module được đọc, bên còn lại xác định package được công bố.
- Giữ module path nhất quán giữa compile và runtime để tránh cấu hình resolution khác nhau.

## 11. Tự kiểm tra

**Tình huống 1:** Module A khai báo `requires B;`. Cạnh dependency được hiểu theo hướng nào?

**Trả lời:** Từ A đến B. A là module phụ thuộc và B là module được yêu cầu; A đọc B.

**Tình huống 2:** A yêu cầu B, B yêu cầu C bằng `requires C;` thông thường. A có thể import class từ C chỉ nhờ quan hệ đó không?

**Trả lời:** Không. A đọc B nhưng không tự động đọc C. A cần khai báo dependency trực tiếp vào C hoặc B phải dùng `requires transitive C;` nếu muốn truyền khả năng đọc.

**Tình huống 3:** Vì sao một dependency phải có mặt trên module path?

**Trả lời:** Module path là nơi Java tìm các module có thể quan sát để giải quyết dependency. Chỉ thị `requires` nêu tên module cần dùng, nhưng không tự cung cấp file module.

**Tình huống 4:** Module app đã `requires com.acme.service;` nhưng compiler không cho import class trong package nội bộ của service. Cần kiểm tra gì?

**Trả lời:** Kiểm tra service có export package đó không và kiểu, thành viên có mức truy cập phù hợp không. Readability không thay thế package export.

**Tình huống 5:** Một module chỉ cần dependency cho compile time. Modifier nào có thể phù hợp?

**Trả lời:** `requires static dependency;`, với điều kiện code runtime không cần class của dependency khi dependency không có mặt.

**Tình huống 6:** A yêu cầu B, B yêu cầu A. Có thể giải quyết bằng cách thêm module path không?

**Trả lời:** Không. Đây là chu trình dependency trong named module graph. Cần thiết kế lại chiều phụ thuộc hoặc tách abstraction chung.

Khi đọc một module descriptor, hãy xem mỗi dòng `requires` như một cạnh có hướng: module hiện tại phụ thuộc vào module được nêu tên. Sau đó kiểm tra modifier, module path, package export và cấu hình resolution để hiểu đầy đủ cách dependency được sử dụng.