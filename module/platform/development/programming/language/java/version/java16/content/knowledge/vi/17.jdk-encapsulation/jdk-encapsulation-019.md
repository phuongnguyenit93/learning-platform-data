# Kiểm thử nâng JDK và thu hẹp dần các ngoại lệ truy cập

Khi nâng ứng dụng từ JDK 16 lên JDK 17 hoặc các JDK mới hơn, một lỗi thường gặp là thư viện dùng reflection để đọc hoặc sửa thành phần nội bộ của JDK. Ứng dụng có thể biên dịch thành công nhưng dừng khi chạy với **InaccessibleObjectException** hoặc **IllegalAccessError**. Lỗi đôi khi chỉ xuất hiện trong ORM, serializer, dependency injection, thư viện bytecode, agent giám sát hoặc bộ test.

Nguyên nhân quan trọng là **strong encapsulation**. JDK 16 đã đặt chế độ đóng gói mạnh làm mặc định nhưng vẫn còn cơ chế nới lỏng cho một số truy cập cũ. Từ JDK 17, cơ chế nới lỏng toàn cục đó bị loại bỏ. Vì vậy, nâng JDK cần có bước rà soát phụ thuộc, kiểm thử trên runtime đích và thu hẹp từng ngoại lệ **--add-opens** hoặc **--add-exports** còn cần thiết.

Trong module Java 16, nội dung này giúp chuẩn bị nâng lên các JDK hiện đại. Trọng tâm là phát hiện phụ thuộc nội bộ, phân loại đúng loại quyền truy cập, thay bằng API được hỗ trợ và quản lý ngoại lệ có phạm vi nhỏ, có người chịu trách nhiệm và có kế hoạch loại bỏ.

## 1. Strong encapsulation thay đổi điều gì?

Module system được giới thiệu từ Java 9 để chia JDK thành các module và kiểm soát package nào được module khác truy cập. Một package có thể tồn tại trong JDK nhưng không được công bố như API công khai. Việc một lớp có thể tìm thấy trên classpath không có nghĩa ứng dụng được quyền truy cập vào mọi package, field hoặc method của lớp đó.

JDK 16 và JDK 17 có khác biệt quan trọng:

| Phiên bản | Hành vi liên quan đến đóng gói |
|---|---|
| JDK 9–15 | Có cơ chế relaxed strong encapsulation để duy trì một số truy cập phản chiếu cũ, thường kèm cảnh báo. |
| JDK 16 | JEP 396 đặt strong encapsulation làm mặc định; vẫn có thể chọn chế độ nới lỏng cho một số package cũ bằng **--illegal-access=permit**. |
| JDK 17 trở đi | JEP 403 loại bỏ khả năng nới lỏng toàn cục. Truy cập nội bộ bị chặn mặc định; **--illegal-access** không còn hiệu lực. |

Điều này ảnh hưởng đến code truy cập field hoặc method không public của API JDK bằng reflection, cũng như code tham chiếu package nội bộ như **sun.*** hoặc **jdk.internal.***.

Ví dụ, thư viện có thể dùng reflection để truy cập field riêng bên trong một lớp thuộc **java.base**. Lệnh **setAccessible(true)** từng hoạt động trong một số cấu hình cũ nhưng trên JDK 17+ có thể ném **InaccessibleObjectException** nếu package chưa được mở cho module của thư viện.

Strong encapsulation giúp JDK thay đổi implementation nội bộ mà không phải giữ tương thích với mọi phụ thuộc không được hỗ trợ. Ứng dụng nên dựa trên API Java SE hoặc API JDK được công bố chính thức.

## 2. Không dùng --illegal-access trong cấu hình hiện đại

**--illegal-access** là cơ chế chuyển tiếp trong quá trình áp dụng module system. Trên JDK 17 trở đi, tùy chọn này bị obsolete và không còn thay đổi quyền truy cập. Dù truyền **permit**, **warn**, **debug** hay **deny**, JVM chỉ có thể phát cảnh báo rằng tùy chọn bị bỏ qua.

Vì vậy:

- Xóa **--illegal-access=permit** khỏi script khởi chạy, service, container và cấu hình triển khai.
- Không thêm **--illegal-access=deny** để thay thế cho kiểm thử trên JDK mới; trên JDK 17+ nó cũng không có tác dụng.
- Không coi việc ứng dụng chạy được trên JDK 16 với cấu hình nới lỏng là bằng chứng tương thích với JDK 17+.
- Chạy trực tiếp bằng JDK đích, không kèm tùy chọn mở toàn cục, để tìm các truy cập cần sửa.

JDK 16 có thể được giữ trong ma trận kiểm thử như mốc so sánh khi di chuyển hệ thống cũ. Không nên dùng chế độ truy cập nới lỏng của JDK 16 làm cấu hình vận hành lâu dài.

## 3. Phân biệt exports, opens và reads

Ba khái niệm này giải quyết ba vấn đề khác nhau trong module system:

| Cơ chế | Cấp quyền gì? | Trường hợp sử dụng |
|---|---|---|
| **exports** | Cho module khác truy cập các kiểu public trong package được xuất. | API public của module cần được module khác gọi trực tiếp. |
| **opens** | Cho phép reflection sâu vào các kiểu và member trong package. | Framework cần đọc field private, constructor hoặc metadata bằng reflection. |
| **requires** / readability | Tạo quan hệ module đọc module khác. | Module cần dùng các kiểu được module phụ thuộc công bố. |

Các tùy chọn dòng lệnh tương ứng:

- **--add-exports**: bổ sung quyền truy cập public vào một package chưa được export.
- **--add-opens**: mở package cho reflection sâu trong runtime.
- **--add-reads**: bổ sung quan hệ đọc giữa các module.

Không dùng **--add-opens** để sửa lỗi thiếu package trong module path, và không dùng **--add-exports** để sửa lỗi reflection vào field private.

### 3.1. exports dành cho truy cập API public

Khi module A cần dùng public type trong package của module B, package đó phải được B export và A phải đọc B.

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

Module ứng dụng khai báo:

~~~java
module com.example.application {
    requires com.example.library;
}
~~~

Nếu package không được export, code có thể gặp lỗi truy cập khi biên dịch hoặc liên kết. **--add-exports** có thể tạm thời bổ sung quyền ở compile-time hoặc runtime, nhưng nếu đó là package nội bộ của JDK thì nên tìm API thay thế.

### 3.2. opens dành cho reflection sâu

Framework như serializer, ORM hoặc dependency injection có thể cần truy cập field private trong package của ứng dụng. Nếu package thuộc module do nhóm phát triển kiểm soát, khai báo mở đúng package cho đúng framework:

~~~java
module com.example.application {
    requires org.example.json;
    exports com.example.application.api;
    opens com.example.application.model to org.example.json;
}
~~~

Trong ví dụ, API public được export riêng, còn model chỉ được mở cho module cần reflection. Không cần mở toàn bộ module nếu framework chỉ đọc một package.

**open module** mở mọi package cho reflection sâu. Chỉ dùng khi thật sự cần hành vi đó trên toàn module; với ứng dụng mới, ưu tiên **opens** có giới hạn theo package.

### 3.3. reads chỉ điều chỉnh đồ thị module

Nếu module A cần đọc module B nhưng module descriptor không khai báo quan hệ phù hợp, **--add-reads** có thể bổ sung cạnh đọc:

~~~bash
java --add-reads com.example.application=ALL-UNNAMED \
  --module-path mods \
  -m com.example.application/com.example.application.Main
~~~

Tùy chọn này không export package và không mở field private. Chỉ dùng khi đã xác định lỗi nằm ở quan hệ readability. Với ứng dụng do mình phát triển, ưu tiên sửa **requires** trong **module-info.java**.

## 4. Phân loại lỗi trước khi thêm ngoại lệ

Không phải mọi lỗi xuất hiện sau khi nâng JDK đều do strong encapsulation. Đọc loại exception, package/module trong thông báo và stack trace trước khi thay đổi JVM options.

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| **InaccessibleObjectException** | Reflection muốn truy cập member không public trong package chưa mở. | Nâng thư viện hoặc mở đúng package cho đúng module bằng **opens** hay **--add-opens** tạm thời. |
| **IllegalAccessError** | Bytecode truy cập kiểu/member không được export hoặc không đủ quyền theo module. | Kiểm tra package export, module readability và dependency; chỉ cân nhắc **--add-exports** khi hiểu rõ API được dùng. |
| Lỗi biên dịch báo package không visible | Source tham chiếu package không export hoặc module chưa được đọc. | Sửa module descriptor hoặc dependency; không mặc định thêm **--add-opens**. |
| **ClassNotFoundException** / **NoClassDefFoundError** | Thiếu dependency, module không được resolve hoặc classpath/module-path sai. | Kiểm tra packaging, module path và dependency graph. |
| **NoSuchMethodError** / **NoSuchFieldError** | Binary được biên dịch với version thư viện khác runtime hoặc API đã thay đổi. | Đồng bộ version dependency và build lại. |
| **NoSuchMethodException** / **NoSuchFieldException** | Reflection tìm member không tồn tại hoặc tên/member đã đổi. | Kiểm tra version framework và code; mở package không tạo ra member đã mất. |

**InaccessibleObjectException** là dấu hiệu trực tiếp của truy cập reflection bị chặn. Với các lỗi khác, phải xác minh nguyên nhân trước khi thêm flag.

## 5. Rà soát phụ thuộc bằng jdeps

**jdeps** là công cụ phân tích dependency trong JDK. Tùy chọn **--jdk-internals** tìm các tham chiếu bytecode đến API nội bộ của JDK.

Ví dụ kiểm tra JAR ứng dụng và các thư viện đi kèm:

~~~bash
jdeps --jdk-internals \
  --class-path 'lib/*' \
  build/inventory-application.jar
~~~

Nếu ứng dụng có nhiều JAR, chạy trên từng JAR của sản phẩm và dependency quan trọng:

~~~bash
jdeps --jdk-internals --class-path 'lib/*' lib/framework-adapter.jar
jdeps --jdk-internals --class-path 'lib/*' lib/vendor-client.jar
~~~

Với ứng dụng modular, chỉ định module path và module cần phân tích:

~~~bash
jdeps --jdk-internals \
  --module-path 'mods:lib' \
  --module com.example.application
~~~

Với multi-release JAR, có thể chỉ định release cần phân tích:

~~~bash
jdeps --jdk-internals \
  --multi-release 25 \
  --class-path 'lib/*' \
  build/inventory-application.jar
~~~

Chạy **jdeps** từ JDK đích hoặc JDK mới tương ứng với release đang kiểm tra. Đọc toàn bộ kết quả và ghi lại dependency nào tham chiếu internal API, lớp nào gọi và version thư viện.

### 5.1. jdeps không phát hiện được mọi reflection

**jdeps** phân tích bytecode tĩnh. Nó không thể bảo đảm phát hiện tất cả truy cập động, đặc biệt khi code:

- Tạo tên class, field hoặc method từ chuỗi cấu hình.
- Gọi **Class.forName**, **getDeclaredField**, **getDeclaredMethod** hoặc **setAccessible** theo nhánh runtime.
- Dùng **MethodHandles.privateLookupIn** để truy cập sâu.
- Nạp plugin hoặc class bằng custom class loader.
- Thực hiện truy cập từ native code hoặc agent.

Vì vậy, kết quả **jdeps** sạch không thay thế kiểm thử integration. Phải chạy các luồng thực tế, bao gồm serialization, ORM, dependency injection, mocking, instrumentation, logging và native integration nếu ứng dụng có dùng.

### 5.2. Kiểm tra module name của thư viện

Khi cần mở package cho một module cụ thể, phải biết chính xác tên module của thư viện. Có thể xem bằng:

~~~bash
jar --describe-module --file lib/example-framework.jar
~~~

Thư viện có thể là explicit module, automatic module hoặc nằm trên classpath trong unnamed module. Không suy ra module name chỉ từ tên file JAR.

## 6. Rà soát source code và thư viện dùng reflection

Sau **jdeps**, rà soát source code và cấu hình để tìm truy cập động. Các từ khóa nên kiểm tra gồm:

~~~text
setAccessible
trySetAccessible
getDeclaredField
getDeclaredMethod
getDeclaredConstructor
privateLookupIn
sun.
jdk.internal.
com.sun.
~~~

Đây là danh sách điểm bắt đầu, không phải kết luận rằng mọi lần xuất hiện đều sai. Một số package **com.sun.*** được công bố trong API cụ thể; cần kiểm tra tài liệu API thay vì chỉ dựa vào tên package.

Kiểm tra cả dependency bắc cầu và công cụ chỉ chạy trong test:

- ORM và persistence provider.
- JSON/XML serializer.
- Dependency injection và framework proxy.
- Mocking, bytecode generation và test runner.
- Agent APM, profiler, coverage và monitoring.
- Thư viện truy cập native hoặc quản lý bộ nhớ.
- Plugin, extension và custom class loader.

Một thư viện có thể chạy tốt trên JDK cũ nhưng dùng reflection nội bộ trong một đường code hiếm gặp. Chỉ nâng version thư viện sau khi kiểm tra release note, yêu cầu JDK tối thiểu và khả năng tương thích với framework còn lại.

## 7. Lập ma trận kiểm thử khi nâng JDK

Chọn các JDK theo chính sách hỗ trợ của sản phẩm và nhà cung cấp runtime. Khi di chuyển từ JDK 16, nên kiểm tra ít nhất mốc JDK 17 vì đây là ranh giới loại bỏ relaxed encapsulation. Sau đó kiểm thử trên từng JDK mà sản phẩm sẽ hỗ trợ, chẳng hạn các bản LTS được chọn và bản feature release nếu sản phẩm có cam kết hỗ trợ.

| Chiều kiểm thử | Các trường hợp |
|---|---|
| JDK | JDK 16 làm baseline so sánh; JDK 17; từng JDK mục tiêu được hỗ trợ. |
| Cách nạp code | Classpath và module path nếu sản phẩm hỗ trợ cả hai. |
| Thành phần | Ứng dụng, dependency trực tiếp, dependency bắc cầu, agent và plugin. |
| Luồng nghiệp vụ | Khởi động, xử lý dữ liệu, serialize/deserialize, persistence, shutdown. |
| Kiểu chạy | Chạy từ IDE, script/service, container và application image đóng gói. |
| Quyền truy cập | Chạy không có ngoại lệ; chạy với ngoại lệ tạm thời đã ghi nhận. |
| Dữ liệu | Dữ liệu mới, dữ liệu cũ, dữ liệu lớn và dữ liệu biên. |

Không chỉ kiểm thử một lệnh **java -jar**. Ứng dụng được đóng gói có thể chạy bằng runtime image riêng, launcher riêng hoặc JVM options khác với môi trường phát triển. Hãy kiểm tra chính artifact mà người dùng sẽ cài.

## 8. Quy trình nâng JDK theo từng vòng

### Vòng 1: tạo baseline trên runtime cũ

Ghi lại:

- JDK vendor, version và build number.
- JVM arguments đang dùng.
- Phiên bản framework và dependency.
- Kết quả unit test, integration test và smoke test.
- Danh sách warning về reflective access hoặc internal API.
- Kết quả **jdeps --jdk-internals**.

Lưu log và artifact để có thể so sánh với runtime mới. Không chỉ lưu thông báo cuối cùng PASS/FAIL.

### Vòng 2: cập nhật dependency trước khi thêm ngoại lệ

Kiểm tra release mới của framework và thư viện đã hỗ trợ JDK mục tiêu. Cập nhật các thành phần dùng reflection hoặc JDK internals trước khi tự thêm JVM option.

Ưu tiên:

1. Nâng framework lên phiên bản hỗ trợ JDK mục tiêu.
2. Thay thư viện đã ngừng duy trì bằng thư viện còn được hỗ trợ.
3. Thay code nội bộ JDK bằng API công khai.
4. Chỉ giữ ngoại lệ khi chưa thể thay đổi dependency và có lý do kỹ thuật rõ ràng.

### Vòng 3: chạy trên JDK đích với cấu hình sạch

Khởi chạy ứng dụng trực tiếp trên JDK mục tiêu và bỏ các tùy chọn mở quyền cũ. Ghi lại stack trace đầu tiên cho từng package/module bị chặn.

Không thêm hàng loạt **--add-opens** ngay khi thấy lỗi đầu tiên. Một flag mở rộng có thể che nhiều lỗi độc lập và làm khó việc xác định thư viện thực sự cần quyền.

### Vòng 4: phân loại và xử lý từng lỗi

Với mỗi lỗi:

1. Xác định module nguồn và package bị chặn.
2. Xác định module đích hoặc thư viện gọi reflection.
3. Xác định thao tác cần quyền: truy cập public type, deep reflection hay readability.
4. Kiểm tra phiên bản mới của thư viện đã khắc phục chưa.
5. Xác định API công khai có thể thay thế không.
6. Nếu phải giữ ngoại lệ, chọn đúng cơ chế và target hẹp nhất.

### Vòng 5: loại bỏ ngoại lệ theo từng bước

Sau khi ứng dụng chạy được:

1. Chạy lại test suite không có flag ngoại lệ.
2. Nếu còn lỗi, thêm lại đúng một ngoại lệ nhỏ nhất để xác định dependency.
3. Nâng hoặc thay dependency, hoặc sửa module descriptor.
4. Gỡ ngoại lệ vừa thử và chạy lại regression.
5. Lặp lại cho đến khi không còn ngoại lệ không cần thiết.

Nếu một ngoại lệ phải tồn tại trong thời gian chuyển tiếp, ghi lý do, owner, phạm vi package/module, test chứng minh và ngày xem xét loại bỏ. Không để ngoại lệ tạm thời trở thành cấu hình không ai quản lý.

## 9. Chọn --add-opens khi thật sự cần deep reflection

**--add-opens** mở một package của module nguồn cho module đích để reflection sâu vào các member không public.

Cú pháp:

~~~text
--add-opens source.module/source.package=target.module
~~~

Ví dụ minh họa một thư viện cũ cần reflection vào package của JDK:

~~~bash
java \
  --add-opens java.base/java.lang=org.example.legacyframework \
  --module-path mods:lib \
  -m com.example.application/com.example.application.Main
~~~

Trong ví dụ:

- **java.base** là module nguồn.
- **java.lang** là package cần mở.
- **org.example.legacyframework** là module đích đã xác định từ dependency.

Tên module đích trong ví dụ phải được thay bằng module name thực tế của thư viện. Flag này cho phép framework truy cập sâu vào package đã nêu; nó không chỉ mở một field duy nhất. Do đó, không mở rộng thêm package khác nếu chưa có lỗi và bằng chứng cụ thể.

### 9.1. Ứng dụng chạy trên classpath

Code trên classpath thuộc unnamed module. Khi không thể chuyển thư viện sang named module, có thể dùng **ALL-UNNAMED**:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -cp 'lib/*:inventory-application.jar' \
  com.example.application.Main
~~~

**ALL-UNNAMED** mở package cho tất cả unnamed module, không chỉ một JAR cụ thể. Đây là phạm vi rộng; chỉ dùng tạm thời khi target module không thể chỉ định cụ thể và phải có kế hoạch loại bỏ.

### 9.2. Ưu tiên opens trong module-info của ứng dụng

Nếu framework cần reflection vào model thuộc module do nhóm phát triển quản lý, khai báo package mở có giới hạn:

~~~java
module com.example.application {
    requires org.example.json;
    opens com.example.application.model to org.example.json;
}
~~~

Cách này mô tả rõ trong module descriptor package nào được mở và cho module nào. Không cần thêm **--add-opens** vào launcher nếu module descriptor đã thể hiện đúng quyền cần thiết.

## 10. Chọn --add-exports khi cần truy cập public type trong package chưa export

**--add-exports** cho phép module đích truy cập public type và public member trong package nguồn vốn không được export.

Cú pháp:

~~~text
--add-exports source.module/source.package=target.module
~~~

Ví dụ minh họa:

~~~bash
java \
  --add-exports java.management/sun.management=org.example.monitor \
  --module-path mods:lib \
  -m com.example.application/com.example.application.Main
~~~

Đây là quyền truy cập public trong package được chỉ định; nó không mở field private cho reflection sâu. Nếu lỗi là **InaccessibleObjectException** do **setAccessible**, **--add-exports** không giải quyết đúng vấn đề.

Tùy chọn này cũng có thể được dùng ở compile-time khi source tham chiếu package đó. Tuy nhiên, truy cập package nội bộ của JDK vẫn phụ thuộc implementation và có thể bị thay đổi hoặc loại bỏ ở release khác. Hãy xem đây là cầu nối chuyển đổi, không phải API ổn định cho sản phẩm mới.

## 11. Dùng --add-reads chỉ khi thiếu quan hệ readability

**--add-reads** thêm quan hệ để module nguồn đọc module đích:

~~~text
--add-reads source.module=target.module
~~~

Ví dụ:

~~~bash
java \
  --add-reads com.example.application=org.example.extension \
  --module-path mods:lib \
  -m com.example.application/com.example.application.Main
~~~

Nó không export package và không mở reflection. Với module do mình phát triển, nên khai báo **requires** trong **module-info.java** để quan hệ dependency được kiểm soát và review cùng source code.

Không thêm đồng thời **--add-reads**, **--add-exports** và **--add-opens** theo kiểu thử vận may. Chọn đúng một cơ chế theo lỗi đã xác định.

## 12. Thu hẹp target và phạm vi ngoại lệ

Một ngoại lệ tốt cần xác định được:

| Thuộc tính | Ví dụ cần ghi |
|---|---|
| Module nguồn | **java.base** |
| Package nguồn | **java.lang** |
| Module đích | Module name của framework |
| Cơ chế | **--add-opens** |
| Dependency | Tên và version thư viện cần reflection |
| Lý do | Framework truy cập metadata trong một luồng cụ thể |
| Phạm vi test | Test nào thất bại nếu bỏ flag |
| Người phụ trách | Team sở hữu dependency hoặc tích hợp |
| Kế hoạch bỏ | Version thư viện hoặc mốc release sẽ loại bỏ |

Thứ tự ưu tiên khi thu hẹp:

1. Không cấp ngoại lệ nếu đã nâng cấp hoặc thay được thư viện.
2. Mở package của ứng dụng bằng **opens** có target cụ thể nếu framework cần truy cập model của ứng dụng.
3. Với package JDK, mở đúng module/package cho đúng named module nếu không còn cách khác.
4. Chỉ dùng **ALL-UNNAMED** khi code chạy trên classpath và không thể xác định target hẹp hơn.
5. Không mở toàn bộ module hoặc nhiều package chỉ để làm test qua.

Một flag như **--add-opens java.base/java.lang=ALL-UNNAMED** có thể cho mọi thư viện trên classpath truy cập sâu vào package đó. Điều này mở rộng bề mặt truy cập và che khuất dependency chưa tương thích.

## 13. Thay JDK internals bằng API được hỗ trợ

Nếu **jdeps** phát hiện tham chiếu nội bộ, hãy tìm API chuẩn hoặc thư viện được duy trì để thay thế.

| Phụ thuộc cũ | Hướng thay thế hiện hành |
|---|---|
| **sun.misc.BASE64Encoder** / **BASE64Decoder** | **java.util.Base64** |
| **sun.misc.Cleaner** | **java.lang.ref.Cleaner** |
| Truy cập field/method private của lớp JDK | API công khai được thiết kế cho chức năng đó; tránh phụ thuộc layout nội bộ. |
| Một số thao tác bộ nhớ qua **sun.misc.Unsafe** | **VarHandle** hoặc Foreign Function & Memory API tùy trường hợp. |
| Tự đọc metadata implementation của JDK | API Java SE hoặc API quản trị được công bố chính thức. |

Không có một API thay thế chung cho mọi cách dùng internal API. Trước khi thay, xác định code đang cần thao tác gì và chọn API đúng với ngữ nghĩa đó. Ví dụ, **VarHandle** không phải bản thay thế tự động cho mọi thao tác native memory hoặc mọi lệnh của **Unsafe**.

Một số package như **sun.misc** và **sun.reflect** vẫn có ngoại lệ trong cơ chế encapsulation, nhưng điều đó không biến chúng thành API công khai ổn định. Các method của **sun.misc.Unsafe** không được hỗ trợ; nhiều thao tác đã có API chuẩn thay thế và các method tương ứng đã bị deprecated for removal trong các JDK mới. Không dựa vào việc một lớp vẫn tồn tại để thiết kế phụ thuộc lâu dài.

## 14. Kiểm tra cấu hình JVM ở mọi nơi khởi chạy

Một ứng dụng có thể chạy qua nhiều lớp cấu hình. Hãy tìm ngoại lệ cũ ở:

- Script khởi chạy **.sh**, **.bat**, **.ps1**.
- Service unit hoặc cấu hình daemon.
- Container image và biến môi trường triển khai.
- **JAVA_TOOL_OPTIONS**, **JDK_JAVA_OPTIONS** và biến cấu hình riêng của ứng dụng.
- Cấu hình launcher do jpackage tạo.
- Cấu hình IDE, test runner, build tool và CI.
- Cấu hình agent APM, profiler, coverage hoặc công cụ giám sát.

Không đặt **--add-opens** toàn cục vào môi trường dùng chung nếu chỉ một ứng dụng cần quyền đó. Cấu hình ngoại lệ nên thuộc launcher hoặc service của đúng ứng dụng, có comment về dependency và lý do.

Với ứng dụng đóng gói bằng jpackage, kiểm tra Java options thực tế được lưu trong cấu hình launcher. Nếu dùng **--java-options** để truyền JVM option khi tạo package, chỉ thêm ngoại lệ đã được xác minh và giữ nó ở đúng ứng dụng.

## 15. Kiểm thử module path và classpath

Module path và classpath có phạm vi quyền khác nhau:

- Module trên module path có tên module riêng; có thể cấp quyền cho module cụ thể.
- Code trên classpath thuộc unnamed module; **ALL-UNNAMED** áp dụng cho mọi unnamed module.
- Một thư viện có thể chuyển từ classpath sang module path và có tên module khác với tên artifact.

Nếu sản phẩm hỗ trợ cả hai cách triển khai, kiểm thử cả hai. Dùng:

~~~bash
java --show-module-resolution \
  --module-path mods:lib \
  -m com.example.application/com.example.application.Main
~~~

Để quan sát module nào được resolve khi ứng dụng khởi chạy. Kiểm tra module name của thư viện bằng **jar --describe-module**, rồi xác minh module descriptor có **requires**, **exports** hoặc **opens** phù hợp.

Không chuyển ứng dụng sang module path chỉ để che một lỗi reflection. Việc modularize cần có kế hoạch dependency và kiểm thử riêng; classpath vẫn có thể dùng được nếu các thư viện tương thích với JDK mục tiêu.

## 16. Kiểm thử trong application image và runtime đóng gói

Ứng dụng chạy tốt khi gọi **java** từ JDK cài trên máy phát triển chưa chắc chạy tốt khi đóng gói. Application image hoặc runtime riêng có thể khác về:

- JDK vendor và build.
- Các module được đưa vào runtime image.
- Launcher options.
- Classpath/module path và thứ tự dependency.
- Agent, native library và plugin.
- Cách service hoặc hệ điều hành khởi chạy ứng dụng.

Với ứng dụng dùng jpackage hoặc jlink, tạo lại artifact bằng JDK mục tiêu rồi chạy smoke test trên máy sạch. Xác nhận không vô tình dùng JDK hệ thống bên ngoài runtime đã đóng gói.

Kiểm thử cả launcher, service, tác vụ nền và luồng đóng ứng dụng. Reflection có thể chỉ xảy ra khi framework khởi tạo một thành phần hoặc khi đọc dữ liệu đặc biệt, không nhất thiết xuất hiện lúc khởi động.

## 17. Ví dụ quy trình xử lý một lỗi reflection

Giả sử khi nâng lên JDK 17, ứng dụng dừng với thông báo:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private final ... accessible:
module java.base does not "opens java.lang" to module org.example.legacyframework
~~~

Không nên thêm ngay một danh sách nhiều package vào JVM options. Xử lý theo trình tự:

1. Đọc stack trace để xác định thư viện gọi **setAccessible**.
2. Xác định version thư viện và kiểm tra bản mới có hỗ trợ JDK mục tiêu không.
3. Nâng thư viện và chạy lại test.
4. Nếu vẫn cần truy cập, xác nhận framework có thực sự phải đọc private member trong **java.lang** hay đang dùng implementation detail không được hỗ trợ.
5. Nếu chưa thể loại bỏ trong release hiện tại, thêm đúng một flag tạm thời cho module đích:

~~~bash
--add-opens java.base/java.lang=org.example.legacyframework
~~~

6. Chạy test chứng minh flag chỉ khắc phục đúng luồng đó.
7. Ghi dependency, owner, lý do và phiên bản dự kiến bỏ flag.
8. Trong release tiếp theo, nâng framework hoặc thay cách xử lý để xóa flag rồi chạy lại toàn bộ regression.

Nếu framework chạy trên classpath, target có thể phải là **ALL-UNNAMED**. Khi đó cần ghi rõ phạm vi rộng hơn và ưu tiên kế hoạch chuyển thư viện sang module có tên hoặc loại bỏ nhu cầu reflection.

## 18. Tự động hóa kiểm tra trong CI

Một pipeline nâng JDK nên có các bước:

1. Chạy **jdeps --jdk-internals** trên ứng dụng và dependency được đóng gói.
2. Lưu kết quả và so sánh với baseline; không để dependency nội bộ mới xuất hiện mà không được review.
3. Chạy compile và test bằng JDK đích.
4. Chạy integration test không có ngoại lệ truy cập.
5. Chạy các test đóng gói bằng runtime thực tế.
6. Kiểm tra danh sách JVM flags trong launcher/service.
7. Chạy thêm bộ test với ngoại lệ chuyển tiếp nếu sản phẩm còn đang thu hẹp dần.
8. Chỉ chấp nhận ngoại lệ có owner, lý do và ngày xem xét.

Ví dụ chính sách CI:

~~~text
if jdeps_reports_new_jdk_internal_dependency:
    require_review

if target_jdk_tests_fail_without_access_flags:
    fail_migration_gate

if an_access_exception_has_no_owner_or_removal_plan:
    fail_release_review

if packaged_runtime_tests_fail:
    fail_release
~~~

Phân tích tĩnh không bắt được toàn bộ reflection. Vì vậy, CI vẫn phải chạy test nghiệp vụ, integration test và smoke test trên runtime đích.

## 19. Tiêu chí hoàn tất nâng JDK

Có thể xem việc nâng JDK đã sẵn sàng khi:

- Ứng dụng chạy trên tất cả JDK mục tiêu được công bố hỗ trợ.
- Dependency trực tiếp và bắc cầu đã được rà soát.
- Không còn tham chiếu internal API mới ngoài danh sách đã được chấp thuận.
- Không dùng **--illegal-access** trong cấu hình.
- Mọi **--add-opens**, **--add-exports** và **--add-reads** đều có lý do, target và owner.
- Các package được mở ở phạm vi hẹp nhất có thể.
- Test chạy được trên classpath/module path theo phạm vi sản phẩm cam kết.
- Application image/runtime đóng gói chạy đúng trên máy sạch.
- Migration, startup, shutdown và các luồng dùng reflection đã được kiểm thử.
- Có kế hoạch loại bỏ ngoại lệ còn lại và kiểm tra lại trong CI.

Mục tiêu không phải đạt số lượng flag bằng không trong một ngày bằng mọi giá. Mục tiêu là hiểu từng quyền đang cấp, giảm phạm vi của nó và loại bỏ những phụ thuộc không được hỗ trợ theo lộ trình có thể kiểm chứng.

## 20. Lỗi thường gặp khi nâng JDK

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng chạy trên JDK 16 nhưng lỗi ở JDK 17 | Dựa vào relaxed encapsulation của JDK 16 | Chạy trực tiếp trên JDK 17+, nâng dependency và xử lý từng lỗi. |
| **--illegal-access=permit** vẫn nằm trong service | Cấu hình JVM cũ chưa được dọn | Xóa tùy chọn; nó không còn tác dụng trên JDK 17+. |
| Thêm **--add-exports** nhưng **setAccessible** vẫn lỗi | Cần deep reflection, không phải truy cập public type | Xác minh nhu cầu; dùng **opens** hoặc **--add-opens** tạm thời. |
| Thêm **--add-opens** nhưng **IllegalAccessError** vẫn xảy ra | Lỗi nằm ở package export hoặc readability | Kiểm tra module graph và chọn **exports**/**--add-exports** hoặc **requires** đúng. |
| Mở **ALL-UNNAMED** nhưng không rõ thư viện nào cần | Ứng dụng có nhiều dependency trên classpath | Dùng stack trace, nâng dependency và thu hẹp module path/target. |
| **jdeps** không báo lỗi nhưng runtime vẫn lỗi | Truy cập được tạo động qua reflection hoặc plugin | Bổ sung integration test và rà soát các API reflection. |
| Chỉ test unit pass | Framework hoặc agent chỉ hoạt động trong integration/runtime | Chạy test trên runtime đóng gói và các luồng thực tế. |
| Thêm nhiều flag làm ứng dụng chạy nhưng không biết flag nào cần | Xử lý lỗi hàng loạt không phân loại | Bỏ tất cả flag thử nghiệm, thêm lại từng flag theo stack trace và test. |
| Nâng JDK nhưng runtime đóng gói vẫn dùng module cũ | Artifact chưa được tạo lại hoặc launcher trỏ sai runtime | Build lại application image và xác minh runtime thực tế. |

## 21. Quy trình thực hành đề xuất

1. Chọn JDK mục tiêu theo chính sách hỗ trợ và ghi rõ vendor/build.
2. Lưu baseline trên JDK 16 để so sánh.
3. Chạy **jdeps --jdk-internals** trên ứng dụng và toàn bộ thư viện đóng gói.
4. Rà soát source và cấu hình có reflection hoặc truy cập internal package.
5. Nâng dependency trước khi thêm JVM option.
6. Chạy trên JDK mục tiêu mà không có ngoại lệ truy cập.
7. Phân loại lỗi theo reflection, export, readability hoặc dependency mismatch.
8. Thay internal API bằng API được hỗ trợ.
9. Nếu còn ngoại lệ, mở đúng package cho đúng module và ghi kế hoạch loại bỏ.
10. Gỡ từng ngoại lệ và chạy lại regression.
11. Build application image/runtime mới và kiểm thử trên máy sạch.
12. Đưa **jdeps**, test matrix và danh sách ngoại lệ vào CI.

## 22. Cách áp dụng trong Java hiện đại

- Xem JDK 17 là mốc quan trọng khi di chuyển từ JDK 16 vì relaxed strong encapsulation toàn cục không còn.
- Dùng **jdeps --jdk-internals** để phát hiện tham chiếu bytecode tới JDK internals; kết hợp kiểm thử để phát hiện reflection động.
- Ưu tiên cập nhật framework và thư viện thay vì duy trì quyền truy cập vào implementation của JDK.
- Dùng **exports** cho API public, **opens** cho deep reflection và **requires** cho quan hệ module.
- Chỉ dùng **--add-exports**, **--add-opens** hoặc **--add-reads** như ngoại lệ có phạm vi cụ thể và có kế hoạch loại bỏ.
- Tránh **ALL-UNNAMED** nếu có thể xác định module đích.
- Xóa **--illegal-access** khỏi cấu hình JDK mới.
- Kiểm thử trên JDK đích, module path/classpath và runtime được đóng gói.
- Theo dõi ngoại lệ trong CI để không phát sinh thêm dependency nội bộ.

Nâng JDK an toàn cần chứng minh ứng dụng không còn dựa vào quyền truy cập nội bộ một cách vô thức. Khi mỗi ngoại lệ đều có nguyên nhân, module đích, phạm vi và kế hoạch loại bỏ, nhóm phát triển có thể nâng JDK theo từng bước mà vẫn kiểm soát được rủi ro tương thích.

## Tài liệu tham khảo

- [Oracle JDK 16 Release Notes — JEP 396: Strongly Encapsulate JDK Internals by Default](https://www.oracle.com/java/technologies/javase/16-relnote-issues.html)
- [Oracle JDK 17 Release Notes — Strong Encapsulation](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html)
- [OpenJDK JEP 396 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [OpenJDK JEP 261 — Module System](https://openjdk.org/jeps/261)
- [Oracle JDK 26 Migration Guide — Strong Encapsulation in the JDK](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html)
- [Oracle JDK 26 — jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Oracle JDK 26 — jar Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html)
- [Oracle JDK 26 API — java.lang.Module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html)
- [Oracle JDK 26 Migration Guide — Run jdeps on Your Code](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html)
