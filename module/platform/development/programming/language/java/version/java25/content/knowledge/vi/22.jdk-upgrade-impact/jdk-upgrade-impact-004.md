# Rà soát phụ thuộc JDK nội bộ, reflective access và tùy chọn JVM không còn hỗ trợ

## 1. Phạm vi và mục tiêu nâng cấp

Bài thuộc chương **Tác động nâng cấp** của module **JAVA_VERSION_JAVA25**. Khi nâng ứng dụng từ JDK cũ lên Java 25 hoặc tiếp tục lên JDK 26/27, một trong những nhóm rủi ro khó phát hiện nhất là dependency vào chi tiết triển khai của JDK: class trong package nội bộ, truy cập private bằng reflection, native access, Java agent attach và các JVM option đã bị loại bỏ hoặc mất tác dụng.

Mã nguồn có thể biên dịch thành công nhưng vẫn lỗi lúc chạy, bởi một thư viện bên thứ ba chỉ thực hiện reflective access khi một endpoint cụ thể được gọi. Tương tự, ứng dụng có thể khởi động trên JDK 25 nhưng thất bại trên JDK 27 vì launcher option cũ đã bị xóa hoặc một module nội bộ đã biến mất.

Bài này lấy JDK 25 làm điểm xuất phát và dùng **JDK 27 làm mốc kiểm tra hiện hành**. Tại ngày 27/11/2026, Oracle đã phát hành JDK 27.0.1.1 ngày 17/11/2026; khi triển khai thực tế, luôn kiểm tra bản cập nhật bảo mật mới nhất của nhà cung cấp JDK đang sử dụng.

Các mục tiêu sau khi học:

1. Phân biệt API Java được hỗ trợ với JDK internal API.
2. Tìm dependency tĩnh vào package nội bộ bằng `jdeps`.
3. Kiểm tra API deprecated for removal bằng `jdeprscan`.
4. Phát hiện native access bằng `jnativescan`.
5. Xác định nguyên nhân `InaccessibleObjectException` và phân biệt `--add-exports` với `--add-opens`.
6. Kiểm tra deep reflection đang sửa field `final`.
7. Kiểm tra JNI, FFM và dynamic agent loading.
8. Rà soát JVM options đã bị loại bỏ, đã obsolete hoặc đang deprecated.
9. Lập ma trận kiểm thử và kế hoạch migration theo từng JDK.
10. Giữ các compatibility flag ở phạm vi nhỏ, có người sở hữu và có thời hạn loại bỏ.

## 2. API được hỗ trợ và JDK internal API

### 2.1. Vì sao dependency vào nội bộ JDK có rủi ro?

Java SE định nghĩa các API công khai mà ứng dụng có thể dựa vào. HotSpot và JDK còn có các package phục vụ triển khai, công cụ hoặc nội bộ runtime. Những package này không phải hợp đồng tương thích dài hạn.

Ví dụ các nhóm dễ xuất hiện trong ứng dụng cũ:

- `sun.*` và `com.sun.*`: nhiều package chứa implementation detail hoặc API riêng của JDK.
- `jdk.internal.*`: package nội bộ của các module JDK.
- Các lớp truy cập trực tiếp layout object, class loader, compiler hoặc GC.
- Reflection vào private field/method của lớp JDK.
- Native code phụ thuộc offset hoặc cấu trúc nội bộ của HotSpot.

Không kết luận mọi class bắt đầu bằng `com.sun` đều là internal API; phải kiểm tra module, tài liệu và trạng thái hỗ trợ của đúng API. Ngược lại, một class có thể truy cập được ở runtime vẫn không có nghĩa nó được hỗ trợ để dùng lâu dài.

Một dependency nội bộ có thể bị:

- Đóng gói (encapsulate) khiến compile hoặc runtime không truy cập được.
- Đổi tên, chuyển package hoặc đổi semantics.
- Xóa khỏi JDK.
- Yêu cầu thêm quyền module hoặc native access.
- Làm công cụ instrumentation/monitoring không hoạt động sau nâng cấp.

### 2.2. Strong encapsulation từ JDK 17

JDK 9 giới thiệu module system. Trong giai đoạn chuyển tiếp JDK 9–16, một số truy cập reflective trái phép vẫn có thể chạy với cảnh báo. Từ JDK 17, JDK áp dụng strong encapsulation mặc định cho các package nội bộ.

Nếu thư viện gọi deep reflection vào private field/method của một lớp trong module JDK mà package không được mở cho nó, thao tác như `setAccessible(true)` có thể ném `InaccessibleObjectException`.

Ví dụ minh họa:

~~~java
Field value = String.class.getDeclaredField("value");
value.setAccessible(true); // Có thể bị chặn bởi strong encapsulation
~~~

Không nên khắc phục bằng cách mở rộng quyền cho toàn bộ JDK. Hãy xác định thư viện nào cần truy cập, package nào bị chặn và liệu thư viện có bản mới dùng API công khai hay không.

Lưu ý: `sun.misc` và `sun.reflect` không nằm trong cùng phạm vi strong encapsulation như các package `java.*`. Điều đó không biến chúng thành API được hỗ trợ. Đặc biệt, các memory-access method của `sun.misc.Unsafe` đã deprecated for removal và phát cảnh báo khi được gọi từ JDK 24 trở lên.

## 3. Kiểm kê dependency trước khi nâng JDK

### 3.1. Chạy jdeps để tìm JDK internal API

`jdeps` phân tích dependency ở mức class/package. Dùng `--jdk-internals` để tìm tham chiếu tĩnh tới JDK internal API:

~~~bash
jdeps --jdk-internals --recursive --multi-release 27 --class-path "lib/*" app.jar
~~~

Ý nghĩa:

- `--jdk-internals`: tìm dependency vào internal API của JDK.
- `--recursive`: đi qua dependency runtime mà công cụ phân tích được.
- `--multi-release 27`: chọn class version phù hợp khi phân tích multi-release JAR cho JDK 27.
- `--class-path`: cung cấp dependency cần thiết để phân giải class.
- `app.jar`: artifact của ứng dụng cần kiểm tra.

Nếu ứng dụng dùng module path, thêm `--module-path` và `--add-modules` theo cấu hình triển khai. Dùng đúng classpath/module path thực tế; thiếu dependency có thể làm kết quả phân tích không đầy đủ.

Ví dụ một cảnh báo có thể cho biết class ứng dụng tham chiếu `sun.misc.Unsafe` hoặc một package `jdk.internal.*`. Ghi nhận cả artifact bên thứ ba tạo ra dependency, không chỉ source code của ứng dụng.

**Giới hạn:** `jdeps` phân tích bytecode dependency tĩnh. Nó không phát hiện đầy đủ truy cập reflection được tạo từ chuỗi tên class/field, method lookup động, cấu hình framework hoặc native code. Không có cảnh báo từ `jdeps` không chứng minh ứng dụng không dùng reflection vào JDK internals.

### 3.2. Dùng jdeprscan để tìm API Java SE deprecated

`jdeprscan` kiểm tra việc sử dụng Java SE API đã deprecated. Khi dùng JDK 27, có thể tập trung vào API deprecated for removal:

~~~bash
jdeprscan --for-removal --class-path "lib/*" app.jar
~~~

Công cụ cần classpath đủ để phân giải dependency. Nếu thiếu class, bổ sung thư viện vào `--class-path` rồi chạy lại.

`jdeprscan` chỉ báo cáo deprecated API được định nghĩa trong Java SE. Nó không thay thế việc kiểm tra API deprecated trong thư viện bên thứ ba. Để phát hiện thay đổi ở dependency, cần kiểm tra release notes và compatibility matrix của từng thư viện.

### 3.3. Dùng jnativescan để tìm JNI và FFM

JDK 27 cung cấp `jnativescan` để tìm việc sử dụng native functionality trong JAR:

~~~bash
jnativescan --release 27 --class-path "app.jar:lib/*"
~~~

Trên Windows, dùng dấu chấm phẩy giữa các đường dẫn:

~~~powershell
jnativescan --release 27 --class-path "app.jar;lib/*"
~~~

Kết quả có thể chỉ ra:

- Class khai báo method `native`.
- Method gọi restricted method của FFM API.
- Module hoặc classpath entry cần được cấp native access.

Có thể chỉ in danh sách module cần native access:

~~~bash
jnativescan --release 27 --class-path "app.jar:lib/*" --print-native-access
~~~

Với ứng dụng dùng module path, cấu hình `--module-path` và `--add-modules` để công cụ phân tích đúng root module và các module phụ thuộc.

### 3.4. Tìm reflection trong source và dependency

Static scanner không thể nhận diện mọi reflective access. Rà soát source, cấu hình và thư viện có khả năng truy cập private member:

~~~bash
rg -n "setAccessible|trySetAccessible|privateLookupIn|sun\\.misc|jdk\\.internal" src
~~~

Tìm trong cấu hình triển khai và build:

- Các chuỗi `--add-opens` và `--add-exports`.
- JVM arguments trong Dockerfile, Helm chart, systemd, script và CI.
- Biến môi trường `JDK_JAVA_OPTIONS` và `JAVA_TOOL_OPTIONS`.
- Java agent, profiler, APM agent, mocking framework và serialization framework.
- Cấu hình reflection của dependency injection, ORM, JSON/XML mapper và framework.

Nếu thư viện chỉ thực hiện reflection khi một chức năng cụ thể chạy, phải kích hoạt chức năng đó trong test. Chỉ chạy startup smoke test thường không đủ.

### 3.5. Lập sổ theo dõi phát hiện

| Phát hiện | Artifact sở hữu | Cách xác minh | Hướng xử lý |
| --- | --- | --- | --- |
| Dependency vào `jdk.internal.*` | Ứng dụng hoặc thư viện | `jdeps --jdk-internals` | Nâng dependency hoặc thay API được hỗ trợ |
| Deep reflection vào `java.*` | Framework/thư viện | Runtime test và stack trace | Nâng thư viện; chỉ dùng `--add-opens` tạm thời |
| API Java SE deprecated for removal | Ứng dụng/dependency | `jdeprscan --for-removal` | Thay bằng API hiện hành |
| JNI hoặc FFM restricted access | Module/JAR | `jnativescan` và runtime deny test | Cấp quyền native access có chủ đích hoặc thay tích hợp |
| Dynamic agent attach | Agent/test tool | `-XX:-EnableDynamicAgentLoading` | Chuyển agent sang startup hoặc opt-in rõ ràng |
| JVM option obsolete/removed | Script/container | Kiểm tra startup command trên JDK đích | Xóa hoặc dùng thay thế được hỗ trợ |

Mỗi dòng cần có owner, mức độ ảnh hưởng, JDK đầu tiên bị ảnh hưởng, cách tái hiện, phương án sửa và điều kiện xóa compatibility flag. Điều này giúp tránh việc một cờ tạm thời tồn tại vô thời hạn trong production.

## 4. Phân biệt exports và opens khi xử lý reflective access

### 4.1. --add-exports: truy cập public type trong package chưa export

Cú pháp:

~~~text
--add-exports <source-module>/<package>=<target-module>
~~~

`--add-exports` cho phép code trong target module truy cập public type/member của package được chỉ định nếu target module đọc source module. Có thể dùng ở compile time và runtime.

Ví dụ ứng dụng trên classpath cần tham chiếu public type trong package nội bộ:

~~~bash
java --add-exports java.management/sun.management=ALL-UNNAMED -jar app.jar
~~~

`ALL-UNNAMED` áp dụng cho code trên classpath. Với ứng dụng modular, chỉ định tên module đích cụ thể để giới hạn phạm vi.

### 4.2. --add-opens: cho phép deep reflection vào package

Cú pháp:

~~~text
--add-opens <source-module>/<package>=<target-module>
~~~

`--add-opens` mở package cho reflection sâu, bao gồm truy cập non-public member bằng reflection. Đây thường là option xuất hiện khi framework dùng `setAccessible(true)`.

Ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Ví dụ này mở package `java.lang` của module `java.base` cho toàn bộ code trên classpath. Chỉ dùng khi đã xác định một dependency cụ thể cần quyền này; không thêm hàng loạt package chỉ để làm cho ứng dụng khởi động.

### 4.3. Hai option không thay thế cho nhau

| Nhu cầu | Option phù hợp | Phạm vi |
| --- | --- | --- |
| Truy cập public type/member trong package chưa export | `--add-exports` | Quyền truy cập public ở package được chỉ định |
| Dùng reflection để truy cập private/protected/package-private member | `--add-opens` | Deep reflection trong package được mở |
| Compile source có tham chiếu public internal type | `--add-exports` khi compile | Không tự mở reflection lúc runtime |
| Reflection vào private member | `--add-opens` lúc runtime | Không làm API trở thành API được hỗ trợ |

Nếu lỗi là `InaccessibleObjectException` khi gọi `setAccessible(true)`, `--add-exports` thường không giải quyết được. Cần xác định package/module và đánh giá `--add-opens` có phải compatibility workaround tạm thời phù hợp hay không.

### 4.4. Xử lý compatibility flag đúng cách

Thứ tự ưu tiên:

1. Nâng thư viện lên bản không cần truy cập internal JDK API.
2. Thay dependency bằng API Java SE được hỗ trợ.
3. Nếu chưa thể nâng cấp ngay, chỉ cấp quyền cho đúng module/package và đúng module đích.
4. Ghi owner, lý do, test chứng minh và phiên bản thư viện cần nâng.
5. Tạo thời hạn xóa flag và kiểm tra lại sau mỗi lần nâng dependency.

Tránh các cấu hình quá rộng như mở mọi package cho `ALL-UNNAMED` hoặc thêm nhiều `--add-opens` mà không có bằng chứng. Mỗi quyền mở rộng làm giảm lợi ích của module encapsulation và có thể che khuất dependency cần sửa.

### 4.5. Không dùng --illegal-access để khôi phục hành vi cũ

`--illegal-access` là option lịch sử dùng cho relaxed strong encapsulation trong JDK 9–16. Nó đã obsolete từ JDK 17 và không khôi phục quyền truy cập trên JDK 25/26/27. Trên JDK 27, option vẫn được chấp nhận nhưng bị bỏ qua và phát cảnh báo.

Hãy xóa option này khỏi startup script. Nếu một thư viện cần compatibility access, xác định chính xác package và dùng `--add-exports` hoặc `--add-opens` trong giai đoạn chuyển tiếp.

## 5. Deep reflection sửa final field

### 5.1. Vì sao đây là thay đổi riêng?

`final` biểu thị field không được thay đổi sau khi khởi tạo theo mô hình Java thông thường. Một số framework cũ dùng deep reflection để ghi private final field khi deserialize hoặc tái tạo object.

JDK 26 bắt đầu cảnh báo khi deep reflection sửa final field. JDK 27 tiếp tục cung cấp cơ chế kiểm soát riêng. Một compatibility flag `--add-opens` có thể giải quyết ranh giới truy cập package, nhưng không tự cấp quyền cho mọi thao tác sửa final field.

### 5.2. Kiểm tra bằng chế độ deny

Chạy test trên JDK 27 với:

~~~bash
java --illegal-final-field-mutation=deny -jar app.jar
~~~

Nếu một module thực hiện final-field mutation trái phép, runtime ném `IllegalAccessException`. Dùng stack trace để tìm thư viện và class thực hiện thao tác.

Nếu một module thực sự cần quyền này trong giai đoạn chuyển tiếp, JDK có option cấp quyền tường minh:

~~~bash
java --enable-final-field-mutation=ALL-UNNAMED -jar app.jar
~~~

Với module path, chỉ định module cụ thể thay vì `ALL-UNNAMED`. Chỉ bật quyền sau khi xác minh framework cần nó và đã đánh giá kế hoạch nâng cấp.

`--illegal-final-field-mutation` là option kiểm tra/chuyển tiếp và được dự kiến loại bỏ trong tương lai. Không đóng gói chế độ `allow` như một giải pháp lâu dài.

### 5.3. Hướng sửa trong thư viện

- Nâng framework serialization/ORM/DI lên phiên bản hỗ trợ JDK đích.
- Ưu tiên constructor, factory hoặc serialization proxy thay vì sửa final field sau khởi tạo.
- Không dùng reflection để thay đổi field final của object đã được publish cho thread khác.
- Kiểm thử record, immutable DTO và object graph sau deserialize.
- Kiểm tra cả luồng production lẫn test; mocking/serialization library có thể là nguồn mutation.

## 6. Unsafe, native access và Java agent

### 6.1. Thay memory-access method của sun.misc.Unsafe

`sun.misc.Unsafe` vẫn còn trong JDK 25/27, nhưng nhiều memory-access method đã deprecated for removal từ JDK 23. Khi gọi các method này, JDK 24 trở lên phát cảnh báo runtime. Không hiểu cảnh báo đó thành việc toàn bộ class `Unsafe` đã bị xóa; phạm vi cảnh báo tập trung vào các memory-access method đã được thay thế.

Chọn API thay thế theo mục đích:

| Nhu cầu cũ | API nên đánh giá |
| --- | --- |
| Truy cập/đọc/ghi field và thao tác atomic trên object Java | `VarHandle` |
| Truy cập memory ngoài heap hoặc native memory | Foreign Function & Memory API (`java.lang.foreign`) |
| Gọi hàm native từ Java | FFM API; giữ JNI nếu cần tương thích và đã cấp native access |
| Base64 nội bộ cũ | `java.util.Base64` |
| CAS/volatile trên field cụ thể | `VarHandle` với access mode tương ứng |

Không thay mọi lời gọi `Unsafe` bằng một API duy nhất. Hãy xác định chính xác thao tác, alignment, memory ordering, lifetime và ownership của vùng nhớ trước khi chuyển đổi. Với FFM, quản lý `Arena`/`MemorySegment` đúng lifecycle để không dùng vùng nhớ sau khi đã đóng.

### 6.2. Native access trong JDK 24 trở lên

JNI và FFM có thể gọi native code hoặc truy cập memory ngoài JVM. Những thao tác load/link native library và các restricted method cần native access được bật tường minh.

Cấp quyền cho module cụ thể:

~~~bash
java --enable-native-access=com.acme.nativebridge -m com.acme.app/com.acme.Main
~~~

Với code chạy trên classpath:

~~~bash
java --enable-native-access=ALL-UNNAMED -jar app.jar
~~~

`ALL-UNNAMED` cấp quyền cho toàn bộ code trên classpath. Với ứng dụng modular, ưu tiên chuyển JAR chứa native integration lên module path và chỉ cấp quyền cho module cần thiết.

JDK 27 vẫn có `--illegal-native-access` để điều khiển cách xử lý truy cập native chưa được cấp quyền:

- `allow`: cho phép và không cảnh báo.
- `warn`: cho phép nhưng cảnh báo lần đầu theo module; đây là mặc định hiện tại.
- `deny`: ném `IllegalCallerException` khi thao tác native access trái phép.

Dùng chế độ deny trong test:

~~~bash
java --illegal-native-access=deny --enable-native-access=com.acme.nativebridge -jar app.jar
~~~

Chỉ thêm module thực sự cần native access. `--illegal-native-access` là cơ chế chuyển tiếp, được dự kiến loại bỏ khi chế độ deny trở thành mặc định; không dùng `allow` như cấu hình production dài hạn.

### 6.3. Dynamic agent loading và Attach API

Java agent/JVM TI agent có thể được nạp lúc JVM khởi động hoặc attach vào một JVM đang chạy.

Khởi chạy agent ngay từ đầu:

~~~bash
java -javaagent:observability-agent.jar -jar app.jar
~~~

Nạp agent sau khi process đã chạy sẽ phát cảnh báo từ JDK 21 theo JEP 451. Mục tiêu của thay đổi là chuẩn bị cho việc dynamic loading bị từ chối mặc định trong một JDK tương lai.

Trong JDK hiện hành, `-XX:+EnableDynamicAgentLoading` là opt-in tường minh để cho phép dynamic agent loading. Có thể chạy test với:

~~~bash
java -XX:-EnableDynamicAgentLoading -jar app.jar
~~~

Nếu một thư viện hoặc test framework đang attach agent ngầm, test có thể thất bại và chỉ ra dependency cần xử lý. Có thể bật trace để tìm nơi dùng Instrumentation API:

~~~bash
java -Djdk.instrument.traceUsage -jar app.jar
~~~

Ưu tiên cấu hình profiler/APM/mocking agent lúc JVM khởi động bằng `-javaagent` hoặc `-agentlib` khi công cụ hỗ trợ. Không thêm `-XX:+EnableDynamicAgentLoading` chỉ để che cảnh báo mà chưa xác định thành phần nào đang attach.

### 6.4. Security Manager đã bị vô hiệu hóa

Security Manager đã bị permanently disabled từ JDK 24. Ứng dụng không thể bật lại nó để kiểm soát quyền truy cập bằng policy như trước. Nếu code gọi `System.setSecurityManager` hoặc dựa vào Security Manager để sandbox plugin, luồng đó phải được thiết kế lại.

Không có một API Java thay thế trực tiếp cho Security Manager. Đối với code không tin cậy, dùng ranh giới tiến trình/OS/container, quyền hệ điều hành tối thiểu, filesystem/network isolation và giao thức giao tiếp có xác thực. Không xem classloader hoặc module boundary là sandbox bảo mật.

## 7. JVM options đã bị xóa, obsolete hoặc deprecated

### 7.1. Phân biệt ba trạng thái

| Trạng thái | Hành vi khi chạy | Cách xử lý |
| --- | --- | --- |
| Removed | JVM/launcher báo option không được nhận diện và có thể dừng khởi động | Xóa option hoặc dùng thay thế được tài liệu xác nhận |
| Obsolete | Option vẫn được nhận nhưng bị bỏ qua, thường có cảnh báo | Xóa khỏi cấu hình; không giả định nó còn tác dụng |
| Deprecated | Option vẫn hoạt động nhưng phát cảnh báo và có thể bị xóa ở release sau | Lập kế hoạch thay thế, kiểm thử trước khi nâng tiếp |

Đừng coi mọi cảnh báo là lỗi giống nhau. Một option obsolete có thể khiến ứng dụng chạy với default khác điều mà người vận hành mong đợi, dù process vẫn khởi động thành công.

### 7.2. Các option bị xóa trong JDK 25

JDK 25 đã loại bỏ các option liên quan Intel Transactional Synchronization Extensions (RTM):

| Option đã bị xóa | Hành động |
| --- | --- |
| `-XX:RTMAbortRatio=` | Xóa; cơ chế RTM locking liên quan không còn được hỗ trợ |
| `-XX:RTMRetryCount=` | Xóa |
| `-XX:+UseRTMDeopt` | Xóa |
| `-XX:+UseRTMLocking` | Xóa |

Nếu các option này còn trong script, JVM có thể báo `Unrecognized VM option`. Không thay chúng bằng một flag GC/locking khác theo phỏng đoán; bỏ cấu hình RTM và benchmark lại trên JVM hiện hành.

### 7.3. Các option bị xóa trong JDK 26

JDK 26 loại bỏ một số launcher option rất cũ:

| Option | Tình trạng |
| --- | --- |
| `-t`, `-tm` | Bị xóa |
| `-Xfuture` | Bị xóa |
| `-checksource`, `-cs` | Bị xóa |
| `-noasyncgc` | Bị xóa |
| `-Xnoagent` | Bị xóa |

Các option này thường còn sót trong script cũ, script của app server hoặc cấu hình build được sao chép qua nhiều năm. Tìm chúng trong startup command, file argument `@args.txt` và cấu hình môi trường trước khi chuyển sang JDK 26/27.

### 7.4. Các launcher option bị xóa trong JDK 27

JDK 27 loại bỏ các option đã deprecated trước đó:

| Option bị xóa | Thay thế hoặc hành động |
| --- | --- |
| `-noclassgc` | Dùng `-Xnoclassgc` nếu thật sự cần chức năng tương ứng |
| `-verifyremote` | Dùng `-Xverify:remote` nếu thật sự cần cấu hình tương ứng |
| `-noverify` | Không có thay thế; xóa option |
| `-Xverify:none` | Không có thay thế; xóa option |

Không tắt bytecode verification để giải quyết lỗi class loading. Nếu ứng dụng chỉ chạy được khi tắt verification, cần điều tra class file, bytecode instrumentation, agent hoặc công cụ build đã tạo ra bytecode không hợp lệ.

### 7.5. JVMCI và Graal JIT bị loại khỏi HotSpot JDK 27

JDK 27 loại bỏ experimental JVM Compiler Interface (JVMCI) khỏi HotSpot. Thay đổi này bao gồm:

- Module `jdk.internal.vm.ci`.
- Module `jdk.graal.compiler` và `jdk.graal.compiler.management`.
- Các JVMCI-specific compilation policy và configure flag.
- Các option có chuỗi `JVMCI`.
- Option `-XX:+UseGraalJIT`.

Nếu startup script hoặc hệ thống build dùng các module/flag này, phải đánh giá lại compiler runtime đang triển khai. Không giả định có thể giữ `-XX:+UseGraalJIT` trên HotSpot JDK 27. Nếu tổ chức cần Graal compiler, hãy chọn distribution/runtime được nhà cung cấp hỗ trợ và theo tài liệu của đúng vendor.

### 7.6. Option obsolete: còn nhận nhưng không còn tác dụng

**`--illegal-access`**

Option này được dùng trong giai đoạn chuyển tiếp JDK 9–16. Nó obsolete từ JDK 17 và trên JDK 27 vẫn chỉ được nhận rồi bỏ qua, kèm cảnh báo. Xóa `--illegal-access=permit`, `warn`, `debug` hoặc `deny` khỏi cấu hình. Các giá trị này không thay thế `--add-exports` hay `--add-opens`.

**`-XX:[+|-]UseCompressedClassPointers`**

Flag này deprecated trong JDK 25 và obsolete trong JDK 27. JVM 27 luôn dùng compressed class pointers cho object; nếu truyền flag cũ, JVM in cảnh báo rằng option bị bỏ qua. Xóa cả dạng bật lẫn tắt khỏi startup command.

### 7.7. Những option đang còn dùng nhưng chuẩn bị bị siết chặt

JDK 27 vẫn có các option chuyển tiếp sau:

| Option | Trạng thái hiện tại | Cách dùng khi nâng cấp |
| --- | --- | --- |
| `--illegal-native-access` | Mặc định `warn`; `deny` ném `IllegalCallerException`; option dự kiến bị xóa trong tương lai | Dùng `deny` trong test, cấp `--enable-native-access` cho module cần thiết |
| `--illegal-final-field-mutation` | Mặc định `warn`; `deny` ném `IllegalAccessException`; option dự kiến bị xóa trong tương lai | Dùng `deny` trong test, chỉ bật `--enable-final-field-mutation` cho module thực sự cần |
| `-XX:+EnableDynamicAgentLoading` | Cho phép dynamic agent attach tường minh | Ưu tiên nạp agent lúc startup; kiểm tra có thể tắt dynamic loading hay không |

Đây chưa phải các option bị xóa trong JDK 27. Chúng là cơ chế giúp ứng dụng phát hiện dependency trước khi default tương lai chặt hơn. Không nhầm `--illegal-native-access=deny` với một option bị loại bỏ: đây là chế độ kiểm tra nên bật trong test/CI.

## 8. Quy trình nâng cấp từ JDK 25 lên JDK 27

### 8.1. Chốt baseline và artifact

Ghi nhận trước khi thay đổi:

- Nhà cung cấp JDK, version/build và kiến trúc runtime.
- Phiên bản JDK dùng để compile và phiên bản dùng để chạy.
- Artifact ứng dụng, dependency trực tiếp và dependency bắc cầu.
- Classpath/module path, native library và Java agent.
- Toàn bộ JVM arguments từ script, container, service manager và biến môi trường.
- Các compatibility flag `--add-opens`, `--add-exports`, `--enable-native-access` và `--enable-final-field-mutation`.

Tại thời điểm soạn bài, Oracle JDK 27.0.1.1 là bản cập nhật GA mới nhất được công bố ngày 17/11/2026. Đây là mốc tham khảo của Oracle JDK; với Temurin, Corretto, Zulu hoặc distribution khác, xác minh build và security update tương ứng của nhà cung cấp.

### 8.2. Chạy trên JDK đích trước khi đổi source

Nếu ứng dụng hiện được compile bằng JDK 25, hãy chạy artifact đó trên JDK 27 trước khi thay đổi code. Bước này giúp phân biệt lỗi runtime/behavior với lỗi do source migration.

Thực hiện theo thứ tự:

1. Dùng đúng JDK 27 của môi trường đích.
2. Chạy startup smoke test và lưu toàn bộ stderr/stdout.
3. Ghi nhận cảnh báo obsolete/deprecated option.
4. Kích hoạt các luồng serialization, reflection, native integration và instrumentation.
5. Chạy integration test với dependency thật.
6. Thu stack trace của mọi `InaccessibleObjectException`, `IllegalAccessException`, `IllegalCallerException` và lỗi khởi động JVM.

Sau khi biết lỗi runtime, mới quyết định nâng dependency, sửa code, đổi JVM option hoặc thay công cụ.

### 8.3. Kiểm tra lại bytecode sau khi sửa

Dùng công cụ từ JDK đích:

~~~bash
jdeps --jdk-internals --recursive --multi-release 27 --class-path "lib/*" app.jar
jdeprscan --for-removal --class-path "lib/*" app.jar
jnativescan --release 27 --class-path "app.jar:lib/*"
~~~

Nếu ứng dụng dùng multi-release JAR, chọn release 27 để phân tích đúng class version mà runtime sẽ tải. Bổ sung module path và dependency thực tế để giảm missing-dependency result.

Sau khi sửa source và nâng dependency, chạy lại các scanner. Không đánh dấu migration hoàn tất chỉ vì ứng dụng khởi động thành công.

### 8.4. Chạy test với chế độ kiểm tra nghiêm ngặt

Một profile kiểm tra có thể dùng:

~~~bash
java \
  --illegal-native-access=deny \
  --illegal-final-field-mutation=deny \
  -XX:-EnableDynamicAgentLoading \
  -jar app.jar
~~~

Profile này giúp phát hiện:

- JNI/FFM restricted operation chưa được cấp native access.
- Deep reflection sửa final field trái phép.
- Công cụ hoặc thư viện cố attach agent sau khi JVM đã chạy.

Nếu một module thực sự cần native access hoặc final-field mutation, cấp quyền cụ thể cho module đó và ghi rõ lý do. Khi test dynamic agent, bảo đảm profiler/APM cần thiết được nạp lúc startup hoặc có cấu hình kiểm thử riêng; đừng vô tình vô hiệu hóa công cụ quan sát mà test đang phụ thuộc.

Các chế độ `deny` và `-XX:-EnableDynamicAgentLoading` dùng để tìm dependency, không phải mặc định là cấu hình production phù hợp cho mọi ứng dụng.

### 8.5. Rà soát command line thực tế của process

Tìm process:

~~~bash
jcmd -l
~~~

Kiểm tra JVM arguments của đúng PID:

~~~bash
jcmd <pid> VM.command_line
jcmd <pid> VM.flags -all
~~~

Nếu ứng dụng có quyền attach, có thể dùng `RuntimeMXBean.getInputArguments()` để ghi lại input arguments trong chẩn đoán. Cần kiểm tra cả `JDK_JAVA_OPTIONS` và `JAVA_TOOL_OPTIONS` vì chúng có thể thêm option ngoài script startup.

Đừng chỉ kiểm tra command line trong terminal của developer. Container entrypoint, systemd unit, Kubernetes environment, app server và CI runner có thể bổ sung option khác.

### 8.6. Nâng dependency và build tool

Với mỗi thư viện có reflective/native/agent integration:

- Kiểm tra release hỗ trợ JDK 27.
- Đọc release notes về strong encapsulation, native access và final-field mutation.
- Nâng phiên bản framework, bytecode generator, ORM, serializer, mocking framework, profiler và APM agent.
- Kiểm tra plugin Maven/Gradle, test runner và code coverage agent.
- Chạy test trên đúng JDK vendor/build sẽ được triển khai.

Không chỉ nâng dependency trực tiếp. Một thư viện bắc cầu có thể chứa bytecode hoặc reflection code đã cũ, dù source ứng dụng không tham chiếu trực tiếp tới nó.

## 9. Xây pipeline kiểm tra tương thích trong CI

### 9.1. Tách static scan và runtime test

Một pipeline migration nên có các bước độc lập:

~~~mermaid
flowchart TD
    A["Build artifact và thu dependency"] --> B["jdeps: JDK internal API"]
    B --> C["jdeprscan: deprecated for removal"]
    C --> D["jnativescan: JNI / FFM"]
    D --> E["Kiểm tra JVM args và environment"]
    E --> F["Chạy test trên JDK đích"]
    F --> G["Native / final-field / agent strict mode"]
    G --> H["Integration test và smoke test"]
    H --> I["Xóa compatibility flag không còn cần"]
    I --> J["Lưu baseline và phê duyệt release"]
~~~

Không gộp toàn bộ kết quả thành một con số pass/fail. Mỗi finding cần được gán owner và phân loại: code ứng dụng, thư viện bên thứ ba, JVM option, native integration hoặc công cụ vận hành.

### 9.2. Kiểm tra option trước khi khởi động ứng dụng

Có thể dùng JDK đích để xác nhận cú pháp và khả năng nhận option:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Với một startup argument file, tạo bản sao kiểm thử và chạy JVM với đúng danh sách option của ứng dụng nhưng thay main class/JAR bằng `-version`. Nếu có option đã bị xóa, JVM sẽ báo lỗi khi parse arguments.

Không dùng môi trường production để thử một danh sách flag chưa xác minh. Kiểm tra riêng option, sau đó chạy ứng dụng trong staging.

### 9.3. Ma trận compile và runtime

| Compile | Runtime | Mục đích |
| --- | --- | --- |
| JDK 25, `--release 25` | JDK 25 | Baseline hiện tại |
| JDK 25, `--release 25` | JDK 27 | Phát hiện runtime incompatibility trước khi recompile |
| JDK 27, `--release 25` | JDK 27 | Xác nhận source vẫn giữ baseline API 25 |
| JDK 27, `--release 27` | JDK 27 | Đánh giá build sau khi nâng toolchain |

`--release` giới hạn API/source target theo release được chọn; nó không mô phỏng đầy đủ runtime JDK cũ. Chạy artifact thực tế trên JDK đích vẫn là bước bắt buộc.

### 9.4. Điều kiện hoàn tất pipeline

- `jdeps --jdk-internals` không còn finding chưa được giải thích.
- `jdeprscan --for-removal` không còn API cần loại bỏ hoặc có kế hoạch xử lý đã duyệt.
- `jnativescan` đã xác định các module cần native access.
- Test strict mode không có native access hoặc final-field mutation ngoài dự kiến.
- Không còn dynamic agent attach ngầm.
- Không còn JVM option bị xóa hoặc obsolete.
- Compatibility flag còn giữ đều có owner, lý do và ngày xem xét/xóa.
- Integration test đi qua các luồng reflection, serialization, ORM, proxy, native library và instrumentation.
- Ghi lại JDK vendor/version/build, startup arguments và kết quả kiểm thử trong release evidence.

### 9.5. Những gì static scan không thể chứng minh

| Công cụ/kiểm tra | Có thể phát hiện | Không chứng minh được |
| --- | --- | --- |
| `jdeps` | Dependency bytecode tĩnh vào JDK internal package | Reflection theo tên chuỗi, logic được tạo runtime, hành vi native |
| `jdeprscan` | Java SE API deprecated | Deprecated API trong thư viện bên thứ ba |
| `jnativescan` | Restricted JNI/FFM calls và native method declaration trong JAR được scan | Native library được nạp qua code ngoài JAR hoặc hành vi phát sinh từ native code |
| Grep source/config | Một số reflection call, JVM flag, agent config | Mọi call path runtime hoặc code trong binary dependency |
| Integration test | Hành vi của các luồng đã thực thi | Luồng chưa được test hoặc môi trường khác biệt |

Vì vậy, kết quả static scan phải kết hợp với runtime test, dependency inventory và quan sát log. Đặc biệt, một ứng dụng có thể không phát hiện reflection lỗi cho đến khi một endpoint hiếm hoặc một nhánh deserialize cụ thể được gọi.

## 10. Bảng chẩn đoán lỗi khi nâng cấp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `InaccessibleObjectException` | Deep reflection vào package không được mở | Nâng thư viện; nếu chưa thể, chỉ mở đúng package/module bằng `--add-opens` |
| `IllegalAccessError` khi gọi class nội bộ | Package không export cho module gọi | Thay API; `--add-exports` chỉ là workaround tạm |
| `NoClassDefFoundError` cho `jdk.internal.*` | Module nội bộ bị xóa/không còn trong runtime | Loại dependency nội bộ hoặc thay integration |
| `Unrecognized VM option` | JVM option đã bị xóa hoặc không tồn tại trên vendor/runtime này | Đối chiếu release notes và loại/thay option |
| Cảnh báo option bị ignored | Option obsolete hoặc không còn tác dụng | Xóa khỏi startup config, xác minh default mới |
| `IllegalCallerException` trong native call | Module chưa được cấp native access trong chế độ deny | Xác định module và cấp `--enable-native-access` tối thiểu |
| `IllegalAccessException` khi deserialize | Framework sửa final field trái phép | Nâng framework; xem lại constructor/factory/proxy |
| Dynamic agent loading warning hoặc test fail | Tool attach agent sau khi JVM chạy | Chuyển sang `-javaagent` lúc startup hoặc cấu hình opt-in có kiểm soát |
| Cảnh báo `Unsafe` memory access | Thư viện gọi memory-access method đã deprecated | Nâng thư viện hoặc thay bằng VarHandle/FFM |
| JVM khởi động trên JDK25 nhưng không trên JDK27 | Option/Module bị loại trong JDK27 | Kiểm tra bảng removed options, JVMCI và classpath/module path |

### 10.1. Ví dụ xử lý một InaccessibleObjectException

Giả sử stack trace chỉ ra thư viện cũ gọi `setAccessible(true)` lên private field trong `java.lang`.

1. Xác định artifact và phiên bản tạo ra stack frame.
2. Kiểm tra release mới của thư viện có bỏ reflective access đó không.
3. Nâng dependency và chạy lại test.
4. Nếu chưa thể nâng ngay, xác định source module, package và target module.
5. Dùng một `--add-opens` đúng package trong staging để xác nhận giả thuyết.
6. Ghi compatibility flag vào danh sách nợ kỹ thuật, đặt deadline nâng dependency.
7. Xóa flag sau khi nâng thư viện và chạy lại integration test.

Không thêm `--add-opens java.base/java.lang=ALL-UNNAMED` cho tất cả môi trường chỉ vì một stack trace từ một thư viện cũ. Flag đó mở quyền rộng cho mọi code trên classpath.

## 11. Bài thực hành: chuẩn bị ứng dụng cho JDK 27

**Tình huống:** một dịch vụ được build bằng JDK 25. Startup script có nhiều JVM flag cũ; một thư viện serialization dùng reflection; ứng dụng gọi native library và test agent attach động. Mục tiêu là chạy trên JDK 27 với ít compatibility exception nhất.

### Phần A — Kiểm kê

1. Ghi lại JDK vendor/version/build.
2. Thu startup command từ container/service.
3. Kiểm tra `JDK_JAVA_OPTIONS` và `JAVA_TOOL_OPTIONS`.
4. Tìm `--add-opens`, `--add-exports` và các flag `-XX`.
5. Lập danh sách thư viện có reflection, JNI, FFM hoặc Java agent.

**Đạt** khi có danh sách artifact và cấu hình JVM thực tế.

### Phần B — Static scan

1. Chạy `jdeps --jdk-internals` với classpath/module path thật.
2. Chạy `jdeprscan --for-removal`.
3. Chạy `jnativescan --release 27`.
4. Lưu output và gán owner cho từng finding.
5. Xác định dependency không thể phân tích do thiếu classpath.

**Đạt** khi không còn finding không rõ nguồn gốc.

### Phần C — Sửa reflective access

1. Chạy integration test trên JDK 27.
2. Thu stack trace của `InaccessibleObjectException`.
3. Nâng serialization framework nếu đã có bản hỗ trợ.
4. Chỉ thêm `--add-opens` tạm thời để xác minh lỗi, ghi owner và deadline.
5. Chạy với `--illegal-final-field-mutation=deny`.
6. Xác minh record/immutable DTO không cần sửa final field sau khởi tạo.

**Đạt** khi các luồng serialize/deserialize hoạt động mà không cần final-field mutation trái phép.

### Phần D — Sửa native và agent access

1. Chạy `jnativescan` để xác định module/JAR cần native access.
2. Chạy với `--illegal-native-access=deny`.
3. Cấp `--enable-native-access` cho module thật sự cần.
4. Chạy với `-XX:-EnableDynamicAgentLoading`.
5. Chuyển agent cần thiết sang startup argument nếu công cụ hỗ trợ.
6. Kiểm tra native library load và shutdown behavior.

**Đạt** khi native access được cấp có chủ đích và không có agent attach ngoài dự kiến.

### Phần E — Dọn JVM options và phát hành

1. Xóa RTM flags đã bị loại trong JDK 25.
2. Xóa launcher options bị loại trong JDK 26/27.
3. Xóa `--illegal-access` và `UseCompressedClassPointers` obsolete.
4. Kiểm tra module/flag JVMCI nếu trước đây dùng Graal JIT.
5. Chạy compile matrix, integration test và smoke test.
6. Lưu JDK build, command line, scanner output và kết quả kiểm thử.

**Đạt** khi ứng dụng chạy trên JDK 27 mà không phụ thuộc vào option đã bị xóa hoặc obsolete.

## 12. Checklist trước khi hoàn tất nâng cấp

### Dependency và API nội bộ

- [ ] Đã chạy `jdeps --jdk-internals` trên ứng dụng và thư viện quan trọng.
- [ ] Đã rà soát reflection theo source, cấu hình và runtime stack trace.
- [ ] Đã chạy `jdeprscan --for-removal` với JDK đích.
- [ ] Đã kiểm tra `sun.misc.Unsafe` memory-access methods.
- [ ] Đã xác định mọi compatibility flag và owner.

### Reflection và module access

- [ ] Đã phân biệt `--add-exports` và `--add-opens`.
- [ ] Không dùng `--illegal-access`.
- [ ] Không mở toàn bộ package/module nếu không có lý do cụ thể.
- [ ] Đã kiểm tra final-field mutation với chế độ deny.
- [ ] Đã nâng framework serialization/ORM/DI/mock nếu cần.

### Native và instrumentation

- [ ] Đã chạy `jnativescan`.
- [ ] Đã bật native access cho module cần thiết.
- [ ] Đã chạy test với `--illegal-native-access=deny`.
- [ ] Đã kiểm tra dynamic agent loading.
- [ ] Agent/profiler được nạp theo cơ chế được hỗ trợ.

### JVM options và release

- [ ] Không còn RTM flags đã bị xóa trong JDK 25.
- [ ] Không còn launcher option bị xóa trong JDK 26/27.
- [ ] Không còn `-noverify` hoặc `-Xverify:none`.
- [ ] Không còn `UseCompressedClassPointers` hoặc `--illegal-access` obsolete.
- [ ] Đã kiểm tra JVMCI/Graal JIT nếu ứng dụng từng dùng.
- [ ] Đã kiểm thử trên đúng vendor/build JDK đích.
- [ ] Đã kiểm tra bản cập nhật bảo mật mới nhất của nhà cung cấp.

## 13. Câu hỏi tự đánh giá

1. Vì sao dependency vào `jdk.internal.*` có rủi ro tương thích?
2. Strong encapsulation áp dụng mặc định từ JDK nào?
3. `jdeps --jdk-internals` phát hiện loại dependency nào?
4. Vì sao `jdeps` không phát hiện đầy đủ reflective access?
5. `jdeprscan` không báo cáo loại deprecated API nào?
6. `jnativescan` giúp kiểm tra JNI/FFM như thế nào?
7. Khác biệt giữa `--add-exports` và `--add-opens` là gì?
8. Vì sao `--illegal-access` không còn khôi phục reflective access?
9. Vì sao `sun.misc.Unsafe` còn tồn tại nhưng vẫn cần migration?
10. API nào thường thay thế memory access của `Unsafe`?
11. Vì sao JDK 26 cảnh báo khi deep reflection sửa final field?
12. `--add-opens` có tự cấp quyền sửa final field không?
13. `--illegal-final-field-mutation=deny` dùng để kiểm tra điều gì?
14. Native access restriction ảnh hưởng JNI và FFM từ JDK nào?
15. Khi nào nên dùng `--enable-native-access`?
16. Vì sao nên ưu tiên cấp native access cho module cụ thể?
17. Dynamic agent loading khác `-javaagent` lúc startup như thế nào?
18. `-XX:-EnableDynamicAgentLoading` giúp phát hiện vấn đề gì?
19. Các RTM option nào đã bị xóa trong JDK 25?
20. Các launcher option cũ nào bị xóa trong JDK 26?
21. Các option nào bị xóa trong JDK 27 và có thay thế?
22. Vì sao `-noverify` và `-Xverify:none` không có thay thế?
23. JDK 27 thay đổi JVMCI/Graal JIT của HotSpot ra sao?
24. Vì sao `UseCompressedClassPointers` bị xem là obsolete trong JDK 27?
25. Tại sao phải chạy artifact trên JDK đích trước khi recompile?
26. Cần kiểm tra những biến môi trường nào có thể thêm JVM options?
27. Vì sao static scan phải kết hợp runtime integration test?
28. Một compatibility flag cần những thông tin gì trước khi được chấp nhận?

## 14. Tài liệu tham khảo

- [Oracle JDK 27 — Migrating from JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): strong encapsulation, add-exports/add-opens, Unsafe, Security Manager, native access và final-field mutation.
- [Oracle JDK 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): native access, final-field mutation, deprecated/obsolete/removed options.
- [Oracle JDK 27 — Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/27all-relnotes.html): JVMCI removal, launcher options bị xóa, UseCompressedClassPointers obsolete và các thay đổi HotSpot.
- [Oracle JDK 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): RTM options bị xóa trong JDK 25.
- [Oracle JDK 25 — Removed Tools and Components](https://docs.oracle.com/en/java/javase/25/migrate/removed-tools-components.html): các API, VM option và thành phần bị xóa/deprecated trong JDK 25.
- [Oracle JDK 26 — Removed Tools and Components](https://docs.oracle.com/en/java/javase/26/migrate/removed-tools-components.html): launcher options và VM options bị xóa/deprecated trong JDK 26.
- [Oracle JDK 27 — jdeps Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html): phân tích dependency và tìm JDK internal API.
- [Oracle JDK 27 — jnativescan Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jnativescan.html): scan JNI, FFM restricted methods và module cần native access.
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/403): strong encapsulation từ JDK 17.
- [OpenJDK JEP 471 — Deprecate the Memory-Access Methods in sun.misc.Unsafe for Removal](https://openjdk.org/jeps/471): lộ trình thay thế memory access của Unsafe.
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): native access restrictions và opt-in cho JNI/FFM.
- [OpenJDK JEP 451 — Prepare to Disallow the Dynamic Loading of Agents](https://openjdk.org/jeps/451): cảnh báo và lộ trình hạn chế dynamic agent loading.
- [OpenJDK JEP 500 — Prepare to Make Final Mean Final](https://openjdk.org/jeps/500): cảnh báo và lộ trình hạn chế final-field mutation bằng deep reflection.
- [OpenJDK JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): Security Manager bị vô hiệu hóa từ JDK 24.













