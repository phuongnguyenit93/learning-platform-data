# Rà soát deep reflection và phụ thuộc vào sửa final

Java dùng `final` để thể hiện trạng thái không thay đổi sau khi object được khởi tạo. Tuy vậy, một số thư viện từng dùng deep reflection để ghi lại giá trị của `final` instance field sau constructor, thường phục vụ dependency injection, mapping, serialization, ORM hoặc test fixture. Cách làm này làm suy yếu giả định bất biến của JVM và có thể khiến tối ưu hóa dựa trên `final` kém tin cậy.

**JEP 500 — Prepare to Make Final Mean Final** bắt đầu cảnh báo hành vi đó trong JDK 26. JDK 27 vẫn giữ chế độ cảnh báo mặc định; một JDK tương lai sẽ mặc định từ chối các mutation không được cấp quyền. Vì vậy, nâng cấp ứng dụng lên JDK 26/27 cần có một đợt audit source, dependency và runtime, sau đó sửa hoặc thay thư viện còn phụ thuộc vào final-field mutation.

## 1. Phạm vi thay đổi của JEP 500

Deep reflection là việc dùng Reflection API để truy cập thành viên không được export/open công khai theo cách thông thường, ví dụ lấy private field bằng `getDeclaredField()` rồi gọi `setAccessible(true)` hoặc `trySetAccessible()`.

Một số method có thể ghi giá trị vào `final` instance field sau khi object đã được khởi tạo:

- `Field.set(Object, Object)` và các overload `setBoolean`, `setByte`, `setChar`, `setInt`, `setLong`, `setFloat`, `setDouble`.
- `MethodHandles.Lookup.unreflectSetter(Field)` để tạo MethodHandle có quyền ghi field được phản chiếu.

Ví dụ hành vi cần rà soát:

```java
Field field = Config.class.getDeclaredField("region");
field.setAccessible(true);
field.set(config, "ap-southeast-1"); // Ghi vào final field sau constructor
```

`setAccessible(true)` hoặc `trySetAccessible()` tự nó chưa phải thao tác sửa giá trị. Cảnh báo xuất hiện khi code thực sự ghi vào final field bằng mutation method. Với MethodHandle, thao tác cần chú ý là `unreflectSetter` trên `Field`.

JEP 500 tập trung vào deep-reflection mutation của **ordinary final instance fields**. Các trường hợp sau không thuộc nhóm field có thể sửa bằng các mutation method này:

| Field | Có thể mutate bằng deep reflection? | Lý do |
| --- | --- | --- |
| `private final` instance field của class thông thường | Có điều kiện | Cần quyền truy cập package và capability mutation |
| `static final` field | Không | Không phải đối tượng final instance field được phép mutate |
| Final field của record | Không | Tính bất biến của record component được bảo vệ |
| Final field của hidden class | Không | Hidden class final fields không cho phép mutation này |
| Final field được gán trong constructor | Có | Đây là khởi tạo bình thường của Java, không phải deep-reflection mutation |

Thay đổi này không cấm Reflection API nói chung. Đọc private field, gọi method private hoặc ghi vào non-final field vẫn chịu các quy tắc truy cập/module tương ứng. Hãy phân biệt lỗi truy cập do module encapsulation với lỗi do final-field mutation.

## 2. JDK 26 và JDK 27 đang xử lý thế nào?

Khi code thực hiện một final-field mutation không được cấp quyền, JDK 26/27 mặc định vẫn cho thao tác chạy nhưng phát cảnh báo. Cảnh báo đầu tiên được phát tối đa một lần cho mỗi module thực hiện mutation; nếu toàn ứng dụng ở class path, các thư viện đó thường thuộc unnamed module nên có thể chỉ thấy một cảnh báo dù có nhiều vị trí mutation.

| Mode | Hành vi | Dùng trong giai đoạn nào? |
| --- | --- | --- |
| `allow` | Cho phép mutation không cảnh báo | Chỉ là biện pháp tạm thời trong lúc điều tra |
| `warn` | Cho phép mutation và cảnh báo lần đầu theo module | Mặc định của JDK 26/27 |
| `debug` | Cho phép mutation, in cảnh báo và stack trace cho từng lần | Điều tra vị trí gọi trong test/staging |
| `deny` | Từ chối mutation trái phép; `Field.set` ném `IllegalAccessException` | CI và staging để kiểm tra sẵn sàng cho tương lai |

`deny` sẽ trở thành mặc định trong một JDK tương lai. Tùy chọn `--illegal-final-field-mutation` cũng là công cụ chuyển tiếp và được dự kiến loại bỏ trong một bản phát hành tương lai; không thiết kế vận hành dài hạn dựa trên `allow` hoặc `warn`.

JDK 27 tiếp tục phát cảnh báo theo JEP 500. Không nên hiểu việc nâng từ 26 lên 27 là đã tự giải quyết các dependency cũ; hãy tiếp tục chạy audit và thử nghiệm `deny`.

## 3. Hai điều kiện độc lập: quyền mở package và capability mutation

Để deep reflection ghi vào một final instance field thông thường, cần thỏa các điều kiện truy cập của Reflection API và có capability final-field mutation cho module gọi.

- **Package openness/access:** package khai báo field phải mở cho module thực hiện deep reflection, hoặc thỏa điều kiện truy cập công khai phù hợp.
- **Mutation capability:** module của code gọi phải được cho phép bằng `--enable-final-field-mutation`.

`--add-opens` chỉ giải quyết quyền truy cập sâu vào package. Nó **không** cấp capability để sửa final field và không tự loại bỏ cảnh báo JEP 500. Ngược lại, `--enable-final-field-mutation` cũng không tự mở package đóng.

Ví dụ module `legacy.mapper` cần sửa field trong package `com.example.model` của module `app.model`:

```bash
java \
  --enable-final-field-mutation=legacy.mapper \
  --add-opens=app.model/com.example.model=legacy.mapper \
  -m app.main/com.example.Main
```

Nếu code gọi nằm trên class path (unnamed module), tùy chọn capability có thể dùng `ALL-UNNAMED`; package vẫn phải được mở cho unnamed modules:

```bash
java \
  --enable-final-field-mutation=ALL-UNNAMED \
  --add-opens=app.model/com.example.model=ALL-UNNAMED \
  -jar application.jar
```

Chỉ dùng các ví dụ này như ngoại lệ có kiểm soát khi dependency chưa thể thay thế. Không thêm `--enable-final-field-mutation=ALL-UNNAMED` hoặc `--add-opens` toàn cục chỉ để xóa cảnh báo mà chưa xác định thư viện và package cần thiết.

## 4. Bắt đầu audit từ runtime JDK 26

Trước khi thay đổi dependency, hãy chạy ứng dụng trên JDK 26 với cấu hình mặc định `warn`. Dùng workload đại diện, không chỉ chạy smoke test khởi động:

```bash
java -jar application.jar
```

Đọc toàn bộ standard error và lưu cảnh báo. Một cảnh báo chứa các thông tin quan trọng:

- Tên field bị mutate và class khai báo field.
- Class thực hiện mutation.
- Module của code gọi.
- Đường dẫn JAR/module chứa code gọi.

Ví dụ cảnh báo có thể chỉ ra `configValue` trong `InternalService` bị `BeanPropertyField` của `library-utils.jar` sửa. Khi đó dependency cần điều tra là `library-utils`, còn class `InternalService` là nơi khai báo field.

Đừng kết luận hệ thống sạch chỉ vì không thấy cảnh báo trong một lần chạy. `warn` chỉ in tối đa một cảnh báo cho mỗi module; đường code mutation cũng có thể chỉ chạy trong profile, luồng deserialize, test hoặc dữ liệu production đặc biệt.

## 5. Dùng debug mode để tìm từng call site

Trong môi trường phát triển hoặc staging, bật `debug` để nhận stack trace cho từng mutation:

```bash
java --illegal-final-field-mutation=debug -jar application.jar
```

Stack trace cho biết call site trong thư viện hoặc code ứng dụng. Ghi lại tối thiểu:

| Thông tin | Dùng để làm gì? |
| --- | --- |
| Declaring class và field | Xác định object model nào đang bị sửa |
| Caller class/module | Xác định thư viện hoặc module thực hiện mutation |
| JAR path/version | Ánh xạ call site về dependency cụ thể |
| Stack trace | Tìm framework feature hoặc code path kích hoạt mutation |
| Test/profile/request | Tái hiện và kiểm chứng sau khi sửa |

Không nên bật `debug` liên tục ở production tải lớn nếu chưa đánh giá lượng log và chi phí quan sát. Dùng nó trong một phiên kiểm thử có kiểm soát, hoặc dùng JFR để thu thập call stack trong workload đại diện.

## 6. Audit bằng JDK Flight Recorder

JFR có event `jdk.FinalFieldMutation`. Event ghi nhận mutation của final instance field qua deep reflection hoặc `Lookup.unreflectSetter(Field)`, bao gồm class khai báo field, tên field và stack trace.

Khởi chạy ứng dụng với recording:

```bash
java \
  -XX:StartFlightRecording:filename=final-field-audit.jfr,settings=default \
  -jar application.jar
```

Chạy các kịch bản nghiệp vụ cần kiểm tra rồi dừng ứng dụng hoặc dump recording. Đọc event:

```bash
jfr print --events jdk.FinalFieldMutation final-field-audit.jfr
```

Để thống kê recording:

```bash
jfr summary final-field-audit.jfr
```

JFR hữu ích khi một lần chạy có nhiều module, nhiều đường code hoặc warning theo module không đủ chi tiết. Event có stack trace nên có thể lần từ field bị sửa tới thư viện gọi. Hãy bảo vệ file recording như log vận hành vì stack trace có thể chứa tên package, class và chi tiết nội bộ.

JFR chỉ ghi nhận các mutation thuộc phạm vi event. Nó không thay thế review source/dependency và không chứng minh mọi đường code đã được thực thi. Một lần audit cần bao phủ các profile và workload liên quan.

## 7. Tìm dấu vết trong source và dependency

Static search giúp tìm các call site trực tiếp trong code do nhóm phát triển quản lý. Ví dụ dùng `rg`:

```bash
rg -n "setAccessible|trySetAccessible|unreflectSetter" src test
rg -n "Field::set|\.setBoolean\(|\.setByte\(|\.setChar\(|\.setInt\(|\.setLong\(|\.setFloat\(|\.setDouble\(" src test
```

Kết quả chỉ là danh sách ứng viên. `setAccessible` có thể chỉ được dùng để đọc field hoặc gọi private method; cần lần tiếp tới thao tác ghi. Ngược lại, framework có thể đóng gói reflection trong helper nên tìm chuỗi không phát hiện hết.

Rà dependency tree để xác định thư viện được dùng trong runtime:

```bash
# Maven
./mvnw dependency:tree

# Gradle
./gradlew dependencies --configuration runtimeClasspath
```

Kết hợp JFR/stack trace với dependency tree, SBOM và thông tin JAR version để xác định dependency bắc cầu. Không chỉ cập nhật dependency trực tiếp: thư viện gây mutation có thể được kéo vào qua framework, ORM, serializer hoặc mocking tool.

## 8. Lập bảng inventory trước khi sửa

Tạo inventory cho từng mutation đã xác nhận:

| Field/class bị sửa | Caller/module | Dependency/version | Luồng kích hoạt | Hướng xử lý | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| `Config.region` | `BeanPropertyField` | `library-utils:1.x` | Bind config | Nâng thư viện hoặc constructor binding | Open |
| `Entity.id` | ORM enhancement | `orm-core:old` | Load entity | Nâng ORM, dùng constructor/factory mapping | Open |
| `Fixture.value` | Test helper | `test-support:old` | Unit test | Dùng constructor hoặc factory trong test | Open |

Phân loại từng trường hợp:

1. **Code do nhóm sở hữu:** sửa trực tiếp và thêm test hồi quy.
2. **Dependency đã có bản sửa:** nâng lên phiên bản hỗ trợ JDK mới, kiểm tra release notes và compatibility matrix.
3. **Dependency không còn được duy trì:** thay thế bằng thư viện còn hỗ trợ hoặc fork có bản sửa được kiểm soát.
4. **Lỗi cần workaround tạm thời:** cô lập module và package cần cấp quyền, ghi owner, lý do, phạm vi và thời hạn loại bỏ.

Không nên thêm cờ runtime trước khi inventory xác định rõ module nào và field nào thực sự cần mutation.

## 9. Thay final-field mutation bằng thiết kế khởi tạo rõ ràng

Giải pháp bền vững là đặt giá trị ngay trong quá trình tạo object, thay vì sửa sau constructor.

### Dùng constructor injection

Trước đây, framework có thể tạo object rồi sửa các final field bằng reflection:

```java
final class ApiClientConfig {
    private final URI endpoint;
    private final Duration timeout;

    ApiClientConfig(URI endpoint, Duration timeout) {
        this.endpoint = endpoint;
        this.timeout = timeout;
    }
}
```

Container nên gọi constructor với dependency đã resolve:

```java
ApiClientConfig config = new ApiClientConfig(endpoint, timeout);
```

Đối với dependency injection framework, ưu tiên constructor injection hoặc factory method được framework hỗ trợ. Không tạo object rỗng rồi gán vào final field sau đó.

### Dùng static factory hoặc builder

Khi object có nhiều tùy chọn:

```java
final class StorageConfig {
    private final Path directory;
    private final int maxEntries;

    private StorageConfig(Path directory, int maxEntries) {
        this.directory = directory;
        this.maxEntries = maxEntries;
    }

    static StorageConfig create(Path directory, int maxEntries) {
        if (maxEntries <= 0) {
            throw new IllegalArgumentException("maxEntries must be positive");
        }
        return new StorageConfig(directory, maxEntries);
    }
}
```

Factory kiểm tra input rồi tạo object đã hoàn chỉnh. Nếu dùng builder, builder giữ state tạm thời; object cuối cùng vẫn nhận mọi final field qua constructor.

### Dùng record cho data carrier phù hợp

```java
record UserSettings(String locale, ZoneId zone, boolean enabled) {}
```

Record phù hợp với dữ liệu bất biến có component rõ ràng. Serializer hoặc mapper cần hỗ trợ canonical constructor của record thay vì ghi trực tiếp vào component field.

### Với serialization và object mapping

- Chọn serializer hỗ trợ constructor/factory hoặc creator annotation.
- Dùng DTO trung gian rồi map sang immutable domain object qua constructor.
- Với ORM, ưu tiên phiên bản/framework có constructor mapping hoặc cơ chế materialization được hỗ trợ.
- Nếu framework yêu cầu mutable entity, cân nhắc field/setter không final cho phần state thực sự cần ORM quản lý; giữ invariant ở domain boundary.

Không chuyển tất cả field thành non-final chỉ để làm cảnh báo biến mất. Hãy chọn mô hình object phù hợp với vòng đời dữ liệu và đảm bảo invariant được kiểm tra tại điểm khởi tạo/cập nhật hợp lệ.

## 10. Xử lý test framework và mocking

Một số test helper hoặc mocking library cũ có thể sửa final field để đưa object về trạng thái tùy ý. Thay thế bằng:

- Constructor/factory fixture tạo object ở trạng thái cần test.
- Builder hoặc fixture factory có API rõ ràng.
- Dependency injection qua constructor để thay collaborator bằng fake/mock.
- Mock construction/static method nếu framework hiện hành hỗ trợ và test thực sự cần.

Không sửa final field trong test chỉ để né thiết kế fixture. Nếu thư viện mocking là nguồn cảnh báo, nâng phiên bản trước và chạy lại toàn bộ test suite, bao gồm test có agent/instrumentation.

## 11. Kiểm thử với deny trước khi triển khai

Sau khi xử lý các warning, chạy toàn bộ test và workload staging với:

```bash
java --illegal-final-field-mutation=deny -jar application.jar
```

Trong CI, nên có một job riêng chạy integration test với `deny`. Nếu test thất bại, stack trace và module liên quan cho biết dependency nào vẫn cần sửa. `deny` chỉ từ chối mutation không được cấp capability; nếu ứng dụng đã bật `--enable-final-field-mutation` cho một module, mutation của module đó vẫn được cho phép khi các điều kiện truy cập khác thỏa mãn.

Ma trận kiểm tra đề xuất:

| Runtime | Mode | Mục tiêu |
| --- | --- | --- |
| JDK 25 | Mặc định | Baseline trước cảnh báo JEP 500; không dùng kết quả này để kết luận đã tương thích |
| JDK 26 | `warn` hoặc `debug` | Tìm module, field và call site đang mutation |
| JDK 26 | `deny` | Phát hiện sớm code sẽ lỗi khi restriction thành mặc định |
| JDK 27 | `warn` | Xác nhận cảnh báo vẫn không xuất hiện sau khi nâng runtime |
| JDK 27 | `deny` | Kiểm tra forward compatibility với chính sách tương lai |

Chạy cả unit test, integration test, startup path, config reload, deserialize, ORM load/save, cache warmup, plugin loading và các luồng chỉ có trong production. Một test pass nhưng chưa đi qua đường code cũ không chứng minh dependency đã sạch.

## 12. Workaround có kiểm soát khi chưa thể thay dependency

Oracle khuyến nghị không dùng hai cờ `--illegal-final-field-mutation` và `--enable-final-field-mutation` trong vận hành lâu dài. Nếu dependency chưa thể cập nhật/thay thế ngay, `--enable-final-field-mutation` là capability cho phép chọn lọc module cần mutation.

Ví dụ tạm thời với một module:

```bash
java \
  --enable-final-field-mutation=legacy.mapper \
  --add-opens=app.model/com.example.model=legacy.mapper \
  --illegal-final-field-mutation=deny \
  -m app.main/com.example.Main
```

Trong cấu hình này, `legacy.mapper` được cấp capability; các module khác vẫn bị kiểm tra theo `deny`. Giữ package mở ở phạm vi đúng package và đúng module. Ghi lại dependency/version, lý do ngoại lệ, owner, thời hạn và issue thay thế. Khi nâng thư viện, xóa cả capability và package opening nếu không còn nhu cầu deep reflection khác.

Với ứng dụng classpath, `ALL-UNNAMED` bao phủ mọi code chạy trong unnamed module, vì vậy phạm vi rộng hơn một thư viện cụ thể. Chỉ dùng khi không thể chạy dependency trong named module riêng; cân nhắc cô lập dependency vào module để thu hẹp quyền.

Không dùng `--illegal-final-field-mutation=allow` để che cảnh báo trên production. Chế độ này làm mất tín hiệu audit và được Oracle khuyến nghị chỉ như biện pháp ngắn hạn trong khi quyết định cách xử lý.

## 13. Đưa chính sách vào Docker, service và deployment

Thử `deny` trong CI trước khi áp dụng vào production. Khi đã xử lý hết dependency, đặt option trong cấu hình launcher của ứng dụng để mọi instance chạy cùng chính sách.

Ví dụ Docker exec form:

```dockerfile
ENTRYPOINT ["java", "--illegal-final-field-mutation=deny", "-jar", "/app/application.jar"]
```

Ví dụ systemd:

```ini
[Service]
ExecStart=/usr/bin/java --illegal-final-field-mutation=deny -jar /opt/app/application.jar
```

Đây là cấu hình kiểm tra trước khi JDK chuyển mặc định sang deny. Khi JDK tương lai bỏ tùy chọn `--illegal-final-field-mutation`, xóa cờ này khỏi launcher; giữ lại những cấu hình capability có chủ đích chỉ khi hệ thống thật sự còn ngoại lệ được hỗ trợ.

Tránh đặt `--enable-final-field-mutation=ALL-UNNAMED` trong `JAVA_TOOL_OPTIONS` ở cấp máy hoặc container base image dùng chung. Biến môi trường đó có thể ảnh hưởng cả process Java con và ứng dụng khác trong cùng môi trường, khiến phạm vi ngoại lệ khó kiểm soát.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
| --- | --- |
| `setAccessible(true)` luôn bị cấm | Nó vẫn phục vụ deep reflection; mutation của final field có thêm policy riêng |
| Chỉ thêm `--add-opens` là sửa được final field | Package openness không cấp final-field mutation capability |
| Bật `--enable-final-field-mutation` tự mở mọi package | Capability và package access là hai điều kiện riêng |
| JDK 27 đã chuyển mặc định sang deny | JDK 27 vẫn cảnh báo; deny là hướng mặc định của một JDK tương lai |
| Không thấy warning nghĩa là không có mutation | Warning mặc định tối đa một lần mỗi module; workload có thể chưa kích hoạt call site |
| Chỉ source code của ứng dụng mới cần rà soát | Framework và dependency bắc cầu thường là nguồn mutation |
| `static final`, record và hidden class field cũng sửa được như field thường | Các nhóm này không thuộc nhóm ordinary final instance field có thể mutate bằng deep reflection |
| `deny` cấm mọi reflection | `deny` chỉ từ chối final-field mutation không được cấp quyền; reflection khác vẫn theo access/module rules |
| JFR thay thế mọi loại audit | JFR ghi nhận mutation thuộc event; vẫn cần source/dependency review và workload coverage |

## 15. Checklist nâng cấp

- [ ] Chạy ứng dụng trên JDK 26 với mặc định `warn` và lưu toàn bộ warning.
- [ ] Chạy `--illegal-final-field-mutation=debug` trong test/staging để lấy stack trace từng mutation.
- [ ] Thu JFR `jdk.FinalFieldMutation` trong workload đại diện.
- [ ] Search source cho `setAccessible`, `trySetAccessible`, `Field.set*` và `unreflectSetter`.
- [ ] Đối chiếu caller với dependency tree, JAR version và module.
- [ ] Phân loại từng trường hợp: code nội bộ, dependency nâng cấp được, dependency cần thay thế hoặc ngoại lệ tạm thời.
- [ ] Ưu tiên constructor/factory/builder/record mapping thay cho sửa final sau khởi tạo.
- [ ] Nâng framework, ORM, serializer, DI và mocking library lên phiên bản hỗ trợ.
- [ ] Chạy unit/integration/production-like tests trên JDK 26 với `deny`.
- [ ] Chạy lại trên JDK 27 với `deny` và kiểm tra toàn bộ deployment profile.
- [ ] Chỉ dùng `--enable-final-field-mutation` cho module thật sự không thể thay, kèm package opening tối thiểu.
- [ ] Ghi owner, lý do, dependency version và deadline cho từng ngoại lệ.
- [ ] Loại bỏ các cờ và package opening không còn cần sau khi nâng dependency.

## Ghi nhớ

- JEP 500 phát cảnh báo từ JDK 26 khi deep reflection mutate ordinary final instance fields; JDK 27 tiếp tục cảnh báo.
- Một JDK tương lai sẽ mặc định từ chối mutation không được cấp quyền.
- Các mutation method cần rà soát là `Field.set*` và `MethodHandles.Lookup.unreflectSetter(Field)`.
- `warn` tối đa một cảnh báo mỗi module; `debug` in stack trace từng lần; `deny` ném `IllegalAccessException` cho mutation trái phép.
- `--add-opens` mở package; `--enable-final-field-mutation` cấp capability. Hai option không thay thế nhau.
- Dùng warning, debug và JFR để tìm thư viện thực hiện mutation; kết hợp dependency tree và source search.
- Ưu tiên nâng/thay dependency hoặc chuyển sang constructor/factory/builder/record mapping.
- Chạy test với `--illegal-final-field-mutation=deny` trên JDK 26/27 trước khi nâng runtime production.
- Chỉ giữ capability tạm thời cho module cụ thể khi không thể thay dependency; tránh `ALL-UNNAMED` nếu có thể cô lập module.
- Không coi `--illegal-final-field-mutation=allow` là giải pháp triển khai dài hạn.

## Tài liệu tham khảo

- [Preparing for Final Field Mutation Restrictions — Oracle JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html) — cảnh báo, các mode, JFR và quy trình migration.
- [Mutation Methods, Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html) — các method có khả năng ghi ordinary final instance field và điều kiện capability.
- [The `java` Command, Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — `--enable-final-field-mutation` và `--illegal-final-field-mutation`.
- [Significant Changes in JDK 26 Release](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html) — JEP 500 trong JDK 26.
- [Significant Changes in JDK 27 Release](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html) — cảnh báo tiếp tục trong JDK 27.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html) — thông tin release chính thức của JDK 27.
- [Avoiding Final Field Mutation — Inside.java](https://inside.java/2026/04/27/avoiding-final-field-mutation/) — các lựa chọn thiết kế thay cho mutation.
- [Quality Outreach Heads-up: JDK 26 Warnings About Final Field Mutation — Inside.java](https://inside.java/2026/05/15/quality-heads-up/) — hướng dẫn cho maintainers thư viện và ứng dụng.
- [JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500) — mục tiêu và lộ trình tăng cường tính bất biến của final fields.
