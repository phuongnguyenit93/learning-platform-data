# Rà soát graph bằng dependency và access evidence

## Mục tiêu

Sau bài này, bạn có thể rà soát module graph của một ứng dụng JPMS bằng bằng chứng từ module descriptor, dependency analysis và runtime; xác định dependency nào là trực tiếp, transitive hoặc chỉ phục vụ implementation; kiểm tra readability, exports và opens theo đúng hướng; phát hiện package hoặc dependency bị lộ ngoài ý muốn; và ghi lại kết luận có thể kiểm chứng trước khi thay đổi kiến trúc.

## 1. Vì sao cần rà soát module graph bằng bằng chứng?

Module graph không chỉ là danh sách các dòng `requires`. Nó mô tả các module được phân giải, quan hệ readability giữa chúng, package được export hoặc open và các service được sử dụng/cung cấp.

Một graph tốt phải trả lời được các câu hỏi:

- Module nào là root của ứng dụng hoặc plugin layer?
- Module nào cần thiết để biên dịch và chạy từng capability?
- Dependency nào xuất hiện trong public API và cần được truyền tiếp?
- Consumer nào thực sự cần đọc module hoặc package khác?
- Package nào phải được mở cho reflection, và module nào là target?
- Provider module nào được thêm vào graph qua service binding?
- Có dependency, export hoặc open nào không còn được sử dụng hoặc đang mở quá rộng?

Không nên kết luận một dependency là thừa chỉ vì tên module không xuất hiện trong một đoạn code ngắn. Dependency có thể được dùng trong public signature, reflection, service loading, resource lookup, generated code hoặc một đường chạy chỉ xuất hiện ở runtime. Hãy kết hợp nhiều nguồn bằng chứng và kiểm tra cả build lẫn runtime.

## 2. Bốn lớp bằng chứng cần thu thập

### Module descriptor

`module-info.java` và `module-info.class` cho biết ý định của module: `requires`, `exports`, `opens`, `uses` và `provides`. Đây là điểm xuất phát để hiểu graph được khai báo.

### Static dependency analysis

Các công cụ như `jdeps` phân tích bytecode để tìm dependency giữa module/package/class. Kết quả giúp phát hiện dependency trực tiếp, dependency tới JDK internal API hoặc sự phụ thuộc chưa được mô tả đúng trong descriptor.

### Runtime resolution

Launcher có thể in thông tin module được phân giải bằng `--show-module-resolution`. Đây là bằng chứng về graph được tạo trong lần khởi chạy cụ thể, với module path, root modules và JVM options cụ thể.

### Runtime access checks

Các API như `Module.canRead`, `Module.isExported` và `Module.isOpen` giúp kiểm tra quan hệ access giữa hai module cụ thể. Đây là bằng chứng về trạng thái runtime, đặc biệt hữu ích khi debug reflection hoặc plugin layer.

Không nguồn nào tự nó trả lời toàn bộ câu hỏi. Descriptor mô tả khai báo, `jdeps` quan sát bytecode, launcher phản ánh lần resolve cụ thể, còn runtime access API kiểm tra một quan hệ cụ thể tại thời điểm chạy.

## 3. Bắt đầu từ descriptor của từng module

Với modular JAR, dùng:

~~~bash
jar --describe-module --file mods/com.acme.orders.jar
~~~

Kết quả cho biết module name và các directive đã được đóng gói. Hãy đối chiếu với source `module-info.java` nếu có; artifact đang chạy mới là thứ quyết định runtime.

Một descriptor ví dụ:

~~~java
module com.acme.orders {
    requires com.acme.money;
    requires transitive com.acme.customer.api;

    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.integration;
    opens com.acme.orders.persistence to org.example.orm;

    uses com.acme.orders.spi.PaymentGateway;
}
~~~

Khi review, phân loại từng directive:

| Directive | Câu hỏi rà soát |
| --- | --- |
| `requires` | Module có thực sự cần dependency này để biên dịch hoặc chạy không? |
| `requires transitive` | Kiểu từ dependency có xuất hiện trong API công khai khiến consumer cần readability không? |
| `requires static` | Dependency có chỉ cần ở compile time hoặc optional ở runtime theo thiết kế không? |
| `exports` | Package có phải API mà consumer được hỗ trợ sử dụng không? |
| Qualified `exports` | Những target module được liệt kê có thực sự cần package này không? |
| `opens` | Framework nào cần deep reflection vào package này? |
| `uses` | Module có thực sự tải service type này không? |
| `provides` | Provider có được đăng ký đúng service type và implementation không? |

Đừng sửa descriptor chỉ để làm output ngắn hơn. Mỗi directive cần có lý do và bằng chứng tương ứng.

## 4. Dùng jdeps để kiểm tra dependency bytecode

Chạy phân tích dependency của một module:

~~~bash
jdeps --module-path mods --check com.acme.orders
~~~

`--check` kiểm tra descriptor và dependency của module, đồng thời có thể gợi ý cách khai báo `requires` phù hợp. Đọc toàn bộ output để phân biệt dependency được khai báo, dependency được tìm thấy trong bytecode và các cảnh báo liên quan.

Xem dependency ở mức module:

~~~bash
jdeps --module-path mods --list-deps --module com.acme.orders
~~~

Xem dependency xuất hiện trong public API:

~~~bash
jdeps --module-path mods --api-only --module com.acme.orders
~~~

`--api-only` hữu ích khi xác định dependency nào lộ ra qua public signature. Nếu module orders trả về kiểu `Money` từ module money, consumer có thể cần readability tới module money. Đây là tình huống cần xem xét `requires transitive`.

Có thể in danh sách module dependency tối thiểu để hỗ trợ tạo runtime image:

~~~bash
jdeps --module-path mods --print-module-deps --module com.acme.orders
~~~

Output của `jdeps` là bằng chứng static từ bytecode được phân tích. Nó không tự biết mọi dependency được nạp động bằng reflection, tên class lấy từ cấu hình, service provider được phát hiện lúc chạy hoặc resource được truy cập theo tên. Hãy xem kết quả như một phần của review, không phải bằng chứng rằng mọi đường chạy đã được bao phủ.

## 5. Phân biệt dependency trực tiếp, transitive và implementation-only

Giả sử:

- `com.acme.orders` dùng `Money` từ `com.acme.money`.
- Public API của orders trả về `Money`.
- `com.acme.client` chỉ khai báo `requires com.acme.orders`.

Descriptor của orders có thể cần:

~~~java
module com.acme.orders {
    requires transitive com.acme.money;
    exports com.acme.orders.api;
}
~~~

Vì kiểu `Money` xuất hiện trong public API của orders, readability tới `com.acme.money` là một phần của hợp đồng mà consumer cần.

Ngược lại, nếu orders chỉ dùng `Money` trong package implementation không export, dependency có thể là:

~~~java
module com.acme.orders {
    requires com.acme.money;
    exports com.acme.orders.api;
}
~~~

Không nên chuyển mọi `requires` thành `requires transitive`. Việc truyền tiếp dependency làm graph của consumer rộng hơn và khiến implementation dependency trở thành một phần của contract.

Với `requires static`, hãy kiểm tra dependency có thật sự optional ở runtime và code có xử lý trường hợp module không hiện diện hay không. Từ khóa `static` không có nghĩa là module system bỏ qua dependency trong mọi bước; nó biểu thị dependency cần ở compile time nhưng có thể không bắt buộc ở runtime.

## 6. Rà soát exports và public surface

Với mỗi package được export, hãy xác định:

1. Consumer nào đang dùng package?
2. Những public type nào thực sự cần được hỗ trợ?
3. Package có chứa implementation class, adapter hoặc persistence detail không?
4. Có thể tách API ra package riêng để giảm bề mặt công khai không?
5. Có nên dùng qualified export thay cho export không giới hạn không?

Ví dụ:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    exports com.acme.orders.spi to com.acme.integration;
}
~~~

`com.acme.orders.api` là public API cho consumer nói chung. SPI chỉ được export cho module integration đã chỉ định.

Đừng nhầm `public` trong Java với việc package được export. Một class public trong package không export vẫn không phải API truy cập thông thường cho module khác. Ngược lại, khi export một package, các public type trong package đó có thể trở thành điểm phụ thuộc của consumer.

Đối với mỗi export, hãy ghi rõ lý do: public API, SPI, compatibility contract hay integration point. Nếu không thể xác định consumer hoặc use case, cần điều tra thêm trước khi xóa export vì có thể consumer nằm ngoài repository hiện tại.

## 7. Rà soát opens và bằng chứng reflection

`opens` cấp quyền deep reflection ở runtime. Đây là một ranh giới riêng với `exports`.

Ví dụ:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    opens com.acme.orders.persistence to org.example.orm;
}
~~~

Khi rà soát, yêu cầu bằng chứng cụ thể:

- Framework nào thực hiện reflection?
- Framework đang chạy trong named module hay unnamed module?
- Package nào chứa field/constructor/method cần truy cập?
- Lỗi runtime hoặc tài liệu framework có chỉ rõ package và target module không?
- Có thể thay reflection bằng API công khai hoặc extension point không?

Nếu framework chạy trong named module, qualified opens thường là lựa chọn rõ ràng:

~~~java
opens com.acme.orders.persistence to org.example.orm;
~~~

Nếu framework chạy trên class path, runtime option có thể là:

~~~bash
--add-opens com.acme.orders/com.acme.orders.persistence=ALL-UNNAMED
~~~

Không mở toàn bộ module chỉ để xử lý một lỗi reflection ở một package. Cũng không xóa opens chỉ vì không thấy lời gọi reflection trong source: framework có thể truy cập field theo metadata, annotation hoặc tên lấy từ cấu hình.

API `Module.isOpen(packageName, targetModule)` giúp kiểm tra trạng thái open hiện tại. Nó không cho biết vì sao package được mở; hãy đối chiếu với descriptor và JVM options.

## 8. Kiểm tra readability và exports theo đúng hướng

Để một module client sử dụng public type trong module API, hai điều kiện quan trọng là readability và export.

Ví dụ:

~~~java
Module client = Client.class.getModule();
Module api = PublicApi.class.getModule();

boolean readable = client.canRead(api);
boolean exported = api.isExported("com.acme.orders.api", client);

System.out.println("readable = " + readable);
System.out.println("exported = " + exported);
~~~

Hướng gọi cần chú ý:

- `client.canRead(api)`: client là module cần đọc API.
- `api.isExported(packageName, client)`: API là module sở hữu package và client là target.

Nếu kiểm tra reflection sâu, dùng:

~~~java
boolean open = api.isOpen("com.acme.orders.persistence", client);
~~~

Một package có thể export nhưng không open. Consumer có thể gọi public API nhưng không được deep-reflect vào private field. Một package open cho reflection cũng không tự động trở thành API public để consumer biên dịch phụ thuộc.

Khi kiểm tra một class cụ thể, bắt đầu từ:

~~~java
Module module = SomeType.class.getModule();

System.out.println("module = " + module.getName());
System.out.println("layer = " + module.getLayer());
System.out.println("loader = " + module.getClassLoader());
~~~

Thông tin layer và class loader hữu ích khi ứng dụng có nhiều module layer hoặc plugin. Hai module cùng tên ở hai layer khác nhau có thể là hai module instance khác nhau.

## 9. Quan sát graph thực tế khi khởi động

Chạy ứng dụng với:

~~~bash
java --show-module-resolution      --module-path mods      --module com.acme.app/com.acme.app.Main
~~~

Launcher sẽ in thông tin quá trình resolve module. Dùng output để xác nhận:

- Root module có đúng không?
- Dependency bắt buộc có được tìm thấy không?
- Module nào được resolve từ module path?
- Có module JDK hoặc provider nào được đưa vào graph?
- Có khác biệt nào giữa môi trường local, test và production không?

Kết quả phụ thuộc chính xác vào module path, root module, parent configuration và JVM options của lần chạy đó. Vì vậy, khi báo cáo một kết luận, ghi lại command hoặc cấu hình launcher đã dùng.

Có thể liệt kê module runtime:

~~~bash
java --module-path mods --list-modules
~~~

Và xem descriptor của module:

~~~bash
java --module-path mods --describe-module com.acme.orders
~~~

Các lệnh này giúp kiểm tra module mà launcher có thể quan sát và descriptor của module cụ thể. Chúng không thay thế việc xác nhận module layer do ứng dụng tự tạo trong runtime nếu ứng dụng dùng dynamic plugin loading.

## 10. Rà soát service binding và provider

Service có thể làm graph runtime rộng hơn những gì nhìn thấy từ các dòng `requires` trực tiếp.

Consumer khai báo:

~~~java
module com.acme.app {
    requires com.acme.spi;
    uses com.acme.spi.Formatter;
}
~~~

Provider khai báo:

~~~java
module com.acme.formatter.upper {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.formatter.upper.UppercaseFormatter;
}
~~~

Khi tạo configuration bằng `resolveAndBind(...)`, module system có thể bind provider module phù hợp vào graph. Nếu chỉ kiểm tra `requires`, bạn có thể bỏ sót provider được thêm thông qua service binding.

Khi review, hãy kiểm tra:

- Consumer có khai báo `uses` đúng service type không?
- Provider có khai báo `provides` đúng interface không?
- Provider có nằm trong module finder được dùng để resolve không?
- Provider có dependency riêng nào cần được phân giải không?
- Runtime layer mà `ServiceLoader` tìm kiếm có chứa provider không?

Có thể kiểm tra configuration bằng `Configuration.modules()` và `findModule(name)`. Việc provider có mặt trong configuration chưa chứng minh provider instance đã khởi tạo thành công; cần kiểm tra service loading trong integration test.

## 11. Phân biệt static evidence và runtime evidence

Một số tình huống thường gây hiểu nhầm:

| Quan sát | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| `jdeps` tìm thấy dependency | Bytecode được phân tích tham chiếu tới module/package đó | Mọi đường chạy runtime đều dùng dependency |
| `jdeps` không thấy dependency | Không tìm thấy dependency tĩnh trong phạm vi phân tích | Không có reflection, service hoặc class name được nạp động |
| Descriptor export package | Package được khai báo export theo target | Mọi consumer đều đọc được module |
| `canRead` trả về true | Module hiện tại có readability tới module đích | Package cụ thể đã được export |
| `isExported` trả về true | Package được export cho target module | Deep reflection vào private member được phép |
| `isOpen` trả về true | Package mở cho deep reflection từ target | Framework đang sử dụng reflection hoặc API có thể thay đổi an toàn |
| `--show-module-resolution` liệt kê module | Module đã được resolve trong lần chạy đó | Mọi provider đều khởi tạo hoặc mọi plugin layer đều giống graph này |

Khi đưa ra kết luận, hãy nói rõ loại bằng chứng và phạm vi của nó. Ví dụ: "jdeps trên artifact release tìm thấy dependency X" khác với "runtime production đã resolve module X" và khác với "consumer Y có thể truy cập package Z".

## 12. Quy trình review module graph có thể lặp lại

Một quy trình thực tế cho từng release:

1. Thu thập modular JAR hoặc exploded module đúng artifact sẽ phát hành.
2. Dùng `jar --describe-module` để ghi nhận descriptor thực tế.
3. Chạy `jdeps --check`, `--list-deps` và `--api-only` cho các module trọng yếu.
4. Đối chiếu dependency bytecode với `requires` và `requires transitive`.
5. Liệt kê mọi `exports`, qualified exports và `opens`, gắn mỗi mục với consumer/framework cụ thể.
6. Kiểm tra `uses`/`provides` và provider được tìm thấy trong configuration.
7. Chạy ứng dụng với `--show-module-resolution` trong môi trường gần production.
8. Dùng runtime access checks hoặc integration test để xác nhận readability, export và open ở các đường truy cập quan trọng.
9. Ghi lại command, JDK version, module path, JVM options và artifact checksum/version để kết quả có thể tái lập.
10. Chỉ đề xuất thay đổi sau khi xác định vấn đề và tác động tới consumer.

Nếu ứng dụng dùng plugin layer được tạo động, bổ sung kiểm tra cho từng loại layer và class loader quan trọng. Graph của boot layer không tự đại diện cho mọi graph do ứng dụng tạo sau đó.

## 13. Cách ghi nhận kết quả review

Một kết luận tốt nên nêu:

- **Subject**: module, package hoặc quan hệ đang được xem xét.
- **Evidence**: descriptor, jdeps output, launcher resolution, runtime check hoặc integration test.
- **Scope**: artifact, JDK version, module path, root module và layer.
- **Finding**: dependency thiếu/thừa, export quá rộng, opens không có căn cứ hoặc access cần thiết chưa được cấp.
- **Impact**: module/consumer nào bị ảnh hưởng và ở compile time hay runtime.
- **Action**: thay đổi descriptor, JVM option, build configuration hoặc giữ nguyên với lý do.
- **Verification**: lệnh/test nào chứng minh thay đổi giải quyết đúng vấn đề.

Ví dụ:

~~~text
Finding: com.acme.orders exports com.acme.orders.internal
Evidence: jar --describe-module shows an unqualified export;
         client module has no documented use of internal types.
Scope: release artifact 2.4, JDK 21, production module path.
Impact: implementation package is part of the accessible module surface.
Action: confirm external consumers, then consider qualified export
        or removing the export in a compatibility release.
Verification: compile supported consumers and run integration tests.
~~~

Đừng ghi "dependency không cần thiết" nếu chỉ dựa trên việc tìm kiếm một tên class trong repository. Có thể có consumer ngoài repository, reflection hoặc service configuration. Nếu chưa có bằng chứng, ghi rõ điều cần xác minh.

## 14. Những sai lầm thường gặp khi review

- **Chỉ đọc `module-info.java`**: bỏ qua descriptor trong artifact thực tế, dependency bytecode và runtime graph.
- **Coi output `jdeps` là toàn bộ runtime dependency**: reflection, service loading và class name động có thể không được thể hiện đầy đủ.
- **Đảo hướng access check**: gọi `api.canRead(client)` thay vì `client.canRead(api)`.
- **Đánh đồng exports với opens**: public API access và deep reflection là hai quyền khác nhau.
- **Xóa opens không có bằng chứng**: framework có thể dùng metadata hoặc reflection động.
- **Giữ exports quá rộng vì "có thể cần sau này"**: public surface trở thành cam kết khó thu hẹp.
- **Thêm transitive cho mọi requires**: làm dependency implementation rò rỉ sang consumer.
- **Chỉ kiểm tra boot layer**: bỏ qua plugin layer hoặc configuration được tạo động.
- **Không ghi lại môi trường chạy**: kết quả resolution có thể khác giữa máy local và production.

## Ghi nhớ

Rà soát JPMS graph cần kết hợp descriptor, static dependency analysis, runtime resolution và access checks. `jdeps` giúp tìm dependency bytecode và dependency trong public API; `jar --describe-module` cho biết descriptor trong artifact; `--show-module-resolution` cho thấy graph của lần chạy cụ thể; `canRead`, `isExported` và `isOpen` kiểm tra quan hệ truy cập theo đúng hướng. Hãy ghi rõ phạm vi và loại bằng chứng trước khi xóa dependency, thu hẹp export hoặc thay đổi opens.
