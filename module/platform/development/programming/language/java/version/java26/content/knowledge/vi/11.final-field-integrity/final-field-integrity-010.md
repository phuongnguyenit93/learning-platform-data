# Phân biệt cảnh báo hiện tại với hạn chế dự kiến trong bản sau

Từ JDK 26, việc dùng deep reflection để ghi vào một trường `final` không còn diễn ra âm thầm: JVM phát cảnh báo khi mã thực hiện thao tác này. Ở JDK 26 và JDK 27, chế độ mặc định vẫn cho phép phép ghi nhưng cảnh báo để nhà phát triển tìm và sửa phụ thuộc. Một bản JDK tương lai dự kiến sẽ từ chối các phép ghi không được cấp quyền, bằng `IllegalAccessException`.

Đây là lộ trình được mô tả trong **JEP 500 — Prepare to Make Final Mean Final**. Mục tiêu là khôi phục ý nghĩa đáng tin cậy của `final`: sau khi đối tượng được khởi tạo, mã khác không thể âm thầm thay đổi các trường final của nó bằng reflection. Điều này hỗ trợ tính đúng đắn, an toàn và các tối ưu hóa JVM dựa trên giả định giá trị final không đổi.

Bài này thuộc module **JAVA_VERSION_JAVA26**. Nội dung tập trung vào cách nhận diện cảnh báo đang có, phân biệt nó với lỗi truy cập reflection, kiểm thử hành vi deny để chuẩn bị cho bản JDK tương lai và xử lý thư viện còn ghi vào final field. Không nên dự đoán một số phiên bản cụ thể cho thời điểm chuyển sang deny mặc định nếu tài liệu phát hành chưa xác nhận.

## 1. Lộ trình từ JDK 25 đến các bản JDK tương lai

| Phiên bản | Hành vi liên quan final field mutation |
|---|---|
| JDK 25 trở về trước | Deep reflection có thể ghi vào một số final instance field nếu vượt qua điều kiện truy cập; thao tác thường diễn ra không có cảnh báo chuyên biệt |
| JDK 26 | Mặc định `--illegal-final-field-mutation=warn`: phép ghi vẫn được cho phép nhưng cảnh báo tối đa một lần cho mỗi module thực hiện mutation |
| JDK 27 | Tiếp tục cảnh báo theo cùng lộ trình JEP 500; vẫn có các tùy chọn kiểm soát và cấp quyền |
| JDK tương lai | Dự kiến deny final field mutation không được cấp quyền theo mặc định; thao tác ghi bị từ chối bằng `IllegalAccessException` |

Điểm quan trọng là JDK 26 không thay đổi cú pháp khai báo `final` và không cấm mọi thao tác reflection. Cảnh báo nhắm vào việc ghi vào final field sau khi đối tượng đã được khởi tạo bằng các cơ chế deep reflection. Đọc final field vẫn được hỗ trợ nếu quyền truy cập hợp lệ.

JDK 27 tiếp tục phát cảnh báo để các thư viện có thêm thời gian di chuyển. Vì vậy, không nên coi việc ứng dụng chạy không lỗi trên JDK 26 hoặc JDK 27 là bằng chứng rằng nó đã tương thích với hạn chế tương lai. Hãy chủ động chạy bộ kiểm thử ở chế độ `deny`.

## 2. Deep reflection ghi final field là gì?

Deep reflection cho phép mã truy cập thành viên không công khai, vượt qua ranh giới truy cập thông thường khi điều kiện module cho phép. Một ví dụ quen thuộc là:

    Field field = SomeClass.class.getDeclaredField("value");
    field.setAccessible(true);
    field.set(target, replacement);

Nếu `value` là final instance field thuộc một lớp thông thường, `Field.setAccessible(true)` thành công chưa có nghĩa là `Field.set(...)` chắc chắn được phép. Từ JDK 26, còn phải có quyền final field mutation cho module của mã đang thực hiện phép ghi.

Các mutation method có liên quan gồm:

- `java.lang.reflect.Field.set(...)` và các phương thức `setBoolean`, `setByte`, `setChar`, `setShort`, `setInt`, `setLong`, `setFloat`, `setDouble`.
- `MethodHandles.Lookup.unreflectSetter(Field)` khi tạo MethodHandle có quyền ghi vào reflected final field.

Cảnh báo JDK 26/27 xác định trường bị thay đổi, lớp khai báo trường và module của mã thực hiện thao tác. Trong thực tế, nguồn mutation thường đến từ thư viện serialization, dependency injection, ORM, mapper, framework kiểm thử hoặc mocking framework.

## 3. Những final field nào có thể được ghi?

JDK không cho phép deep reflection ghi mọi trường final. Cần phân biệt trường có thể được cấp quyền mutation với trường không thể sửa đổi bằng các mutation method của Reflection API.

| Loại trường | Quyền ghi bằng `Field.set` sau khi bật deep reflection |
|---|---|
| Final instance field trong lớp thông thường | Có thể được phép nếu đáp ứng đầy đủ điều kiện truy cập và final field mutation được bật cho caller |
| Static final field | Không cho phép ghi |
| Final field khai báo trong record | Không cho phép ghi |
| Final field khai báo trong hidden class | Không cho phép ghi |
| Final instance field nhưng package chưa mở cho caller | Không thể ghi; trước hết không vượt qua được điều kiện deep reflection |

Các giới hạn static final, record và hidden class không được bỏ qua bằng `--enable-final-field-mutation`. Tùy chọn này không biến một trường vốn không thể sửa đổi thành trường có thể ghi.

Việc thay đổi một final instance field sau khi đối tượng đã được công bố cho mã khác cũng có thể tạo hành vi khó dự đoán. Các luồng khác hoặc mã đã được JIT tối ưu có thể tiếp tục quan sát giá trị cũ. Vì vậy, không sử dụng reflective mutation như cơ chế cập nhật trạng thái đối tượng trong ứng dụng.

## 4. Có hai điều kiện riêng: mở package và bật quyền mutation

Một trong những nhầm lẫn phổ biến nhất là nghĩ rằng `--add-opens` sẽ cho phép ghi final field. Thực tế có hai lớp kiểm soát độc lập:

1. **Quyền deep reflection:** caller phải có thể truy cập thành viên của lớp khai báo trường. Điều này có thể cần `opens` trong module descriptor hoặc `--add-opens` khi chạy.
2. **Quyền final field mutation:** module chứa mã thực hiện phép ghi phải được bật bằng `--enable-final-field-mutation`, hoặc phép ghi sẽ được xử lý theo `--illegal-final-field-mutation`.

Ví dụ, package của module `model.module` được mở cho module thực hiện reflection là `injector.module`:

    module model.module {
        opens com.example.model to injector.module;
    }

Sau đó, JVM cần bật quyền mutation cho module ghi:

    java --enable-final-field-mutation=injector.module \
         --module-path mods \
         -m injector.module/com.example.injector.Main

Nếu không muốn sửa `module-info.java`, có thể mở package lúc khởi chạy:

    java --add-opens=model.module/com.example.model=injector.module \
         --enable-final-field-mutation=injector.module \
         --module-path mods \
         -m injector.module/com.example.injector.Main

`--add-opens` giải quyết quyền truy cập reflection vào package. `--enable-final-field-mutation` giải quyết quyền ghi final field của mã trong module `injector.module`. Một tùy chọn không thay thế tùy chọn còn lại.

Với mã chạy trên class path, module của mã ứng dụng là unnamed module. Có thể bật quyền cho toàn bộ mã trên class path bằng:

    java --enable-final-field-mutation=ALL-UNNAMED -cp app.jar com.example.Main

Đối với package thuộc một named module, vẫn cần package đó mở cho caller theo quy tắc module. Việc bật `ALL-UNNAMED` không tự mở mọi package của các named module.

## 5. Tái hiện cảnh báo trên JDK 26

Ví dụ sau tạo một lớp có final instance field và dùng reflection để ghi vào trường đó. Đây là mã kiểm thử để quan sát cảnh báo; không phải mẫu thiết kế ứng dụng.

    import java.lang.reflect.Field;

    final class RuntimeSettings {
        private final String endpoint;

        RuntimeSettings(String endpoint) {
            this.endpoint = endpoint;
        }

        String endpoint() {
            return endpoint;
        }
    }

    public class FinalFieldMutationProbe {
        public static void main(String[] args) throws Exception {
            RuntimeSettings settings =
                    new RuntimeSettings("https://api.example.test");

            Field field =
                    RuntimeSettings.class.getDeclaredField("endpoint");

            field.setAccessible(true);
            field.set(settings, "https://other.example.test");

            System.out.println("Probe completed");
        }
    }

Biên dịch bằng JDK 26:

    javac -d out src/FinalFieldMutationProbe.java

Chạy bằng JDK 26 ở chế độ mặc định:

    java -cp out FinalFieldMutationProbe

JVM sẽ phát cảnh báo về việc final field `endpoint` bị thay đổi bằng reflection. Trong chế độ mặc định `warn`, phép ghi vẫn được phép thực hiện nếu các điều kiện truy cập và mutation khác đều hợp lệ. Cảnh báo được phát tối đa một lần cho mỗi module thực hiện mutation.

Không nên dùng giá trị được in ra từ getter làm bằng chứng về hành vi ứng dụng. Việc sửa final field sau khởi tạo có thể dẫn đến khác biệt giữa giá trị quan sát qua reflection và giá trị mà mã đã biên dịch/JIT tối ưu đọc được. Mục đích của probe chỉ là phát hiện đường code đang thực hiện phép ghi.

## 6. Bốn chế độ của --illegal-final-field-mutation

JDK 26 cung cấp tùy chọn `--illegal-final-field-mutation` để điều khiển cách JVM xử lý phép ghi không được cấp quyền:

| Giá trị | Hành vi |
|---|---|
| `allow` | Cho phép phép ghi không được cấp quyền, không phát cảnh báo |
| `warn` | Cho phép phép ghi và phát cảnh báo tối đa một lần cho mỗi module; đây là mặc định từ JDK 26 |
| `debug` | Cho phép phép ghi, phát cảnh báo kèm stack trace cho từng lần mutation |
| `deny` | Từ chối phép ghi không được cấp quyền; `Field.set` ném `IllegalAccessException` |

Chạy probe với chế độ debug:

    java --illegal-final-field-mutation=debug -cp out FinalFieldMutationProbe

Chế độ này hữu ích khi cần biết stack trace của từng lần mutation, đặc biệt nếu nhiều thư viện cùng thực hiện thao tác.

Chạy probe ở chế độ deny:

    java --illegal-final-field-mutation=deny -cp out FinalFieldMutationProbe

Nếu module thực hiện mutation chưa được bật quyền, phép ghi sẽ thất bại bằng `IllegalAccessException`. Đây là phép thử quan trọng để tìm lỗi trước khi JDK chuyển sang deny mặc định.

Tùy chọn `--illegal-final-field-mutation` là công cụ chuyển tiếp và được tài liệu JDK đánh dấu sẽ bị loại bỏ trong một bản phát hành tương lai. Không xây dựng cấu hình production dài hạn dựa vào `allow` hoặc `warn`; dùng chúng để điều tra và di chuyển mã.

## 7. Khi nào dùng --enable-final-field-mutation?

`--enable-final-field-mutation` cho phép module được chỉ định thực hiện mutation final field khi các điều kiện reflection khác đã thỏa mãn.

Với named modules:

    java --enable-final-field-mutation=legacy.mapper,legacy.orm \
         --module-path mods \
         -m application.module/com.example.Main

Với class path:

    java --enable-final-field-mutation=ALL-UNNAMED \
         -cp app.jar com.example.Main

Tùy chọn này chỉ nên dùng khi thư viện thực sự cần ghi final field và hiện chưa thể loại bỏ, thay thế hoặc nâng cấp thư viện đó. Nên cấp quyền cho đúng named module cần thiết thay vì bật cho toàn bộ class path.

Có thể kết hợp quyền chọn lọc với chế độ deny để mọi module còn lại bị kiểm tra nghiêm ngặt:

    java --illegal-final-field-mutation=deny \
         --enable-final-field-mutation=legacy.mapper \
         --module-path mods \
         -m application.module/com.example.Main

Trong ví dụ, module `legacy.mapper` được phép thực hiện mutation cần thiết. Các module khác không có quyền này sẽ bị từ chối nếu cố ghi final field.

Việc bật quyền không làm cho thao tác mutation trở nên an toàn hoặc được khuyến nghị. Nó chỉ là ngoại lệ có kiểm soát để ứng dụng tiếp tục chạy trong thời gian di chuyển. Quyền này cũng không cho phép sửa static final field, record field hoặc hidden-class field.

## 8. Phân biệt các lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
|---|---|---|
| `WARNING: Final field ... has been mutated reflectively` | Mutation được phép trong chế độ warn nhưng caller chưa được cấp quyền final field mutation | Tìm thư viện và call site; chạy debug hoặc JFR |
| `InaccessibleObjectException` khi gọi `setAccessible(true)` | Package không mở cho module caller hoặc điều kiện truy cập deep reflection không thỏa mãn | Kiểm tra `opens`, `--add-opens` và module chứa lớp khai báo |
| `IllegalAccessException` khi gọi `Field.set(...)` | Chế độ deny, caller chưa được bật quyền mutation hoặc trường vốn không thể sửa đổi | Kiểm tra `--enable-final-field-mutation` và loại trường |
| `IllegalArgumentException` khi gọi `Field.set(...)` | Đối tượng nhận không đúng kiểu hoặc giá trị không tương thích với kiểu trường | Kiểm tra receiver và kiểu giá trị |
| `setAccessible(true)` thành công nhưng `Field.set(...)` thất bại | Quyền truy cập reflection và quyền final field mutation là hai điều kiện riêng | Bật quyền mutation có chọn lọc nếu thật sự cần; không chỉ thêm `--add-opens` |

Đặc biệt, `InaccessibleObjectException` và `IllegalAccessException` không có cùng ý nghĩa. Lỗi thứ nhất thường xảy ra khi chưa thể mở quyền truy cập reflection. Lỗi thứ hai có thể xuất hiện ở bước ghi final field khi caller không có quyền mutation hoặc trường thuộc nhóm không thể sửa.

## 9. Tìm thư viện thực hiện mutation bằng stack trace và JFR

Cảnh báo thường xuất hiện trong lúc chạy ứng dụng chứ không xuất hiện khi biên dịch. Một thư viện có thể thực hiện mutation trong quá trình khởi tạo object, deserialize dữ liệu, inject dependency hoặc chạy test. Vì vậy, cần kiểm tra cả ứng dụng thực tế và bộ kiểm thử tích hợp.

### Dùng chế độ debug

Chạy toàn bộ ứng dụng hoặc test suite với:

    java --illegal-final-field-mutation=debug -jar application.jar

Mỗi phép mutation sẽ phát cảnh báo và stack trace. Tìm frame đầu tiên thuộc thư viện hoặc mã dự án của bạn để xác định nơi cần nâng cấp hoặc thay đổi.

### Dùng Java Flight Recorder

JFR có event **`jdk.FinalFieldMutation`** ghi nhận final instance field bị thay đổi qua deep reflection hoặc MethodHandle setter được tạo từ reflected field. Event chứa lớp khai báo, tên field, thread và stack trace.

Bắt đầu recording:

    java -XX:StartFlightRecording:filename=final-field-mutation.jfr,dumponexit=true \
         -cp out FinalFieldMutationProbe

Sau khi chương trình kết thúc, xem các event:

    jfr print --events jdk.FinalFieldMutation final-field-mutation.jfr

Có thể bật recording cho một phiên kiểm thử tích hợp dài hơn để phát hiện thư viện chỉ thực hiện mutation trong những luồng nghiệp vụ ít gặp. Không cần thay đổi logic ứng dụng chỉ để thu thập event.

Khi rà soát kết quả, ghi lại ít nhất:

- Tên module thực hiện mutation.
- Lớp và tên final field bị thay đổi.
- Thư viện và phiên bản chứa call site.
- Chức năng nghiệp vụ kích hoạt mutation.
- Phiên bản thư viện thay thế hoặc phương án sửa mã.

## 10. Di chuyển thư viện còn ghi final field

Ưu tiên xử lý theo thứ tự sau:

1. **Nâng cấp thư viện:** kiểm tra phiên bản mới có bỏ reflective final field mutation hoặc đã hỗ trợ JDK 26 trở lên chưa.
2. **Dùng constructor hoặc factory:** truyền giá trị ngay lúc tạo object thay vì tạo object rồi ghi final field.
3. **Sửa mô hình dữ liệu:** nếu giá trị thực sự cần thay đổi trong vòng đời object, thiết kế trường đó là mutable với đồng bộ phù hợp thay vì khai báo final rồi sửa bằng reflection.
4. **Dùng API serialization được hỗ trợ:** kiểm tra cách thư viện khôi phục object có tương thích với cơ chế final field integrity hiện hành hay không.
5. **Thay thế framework cũ:** nếu framework không còn được duy trì và không có kế hoạch hỗ trợ, cân nhắc thay thế.
6. **Cấp quyền tạm thời có phạm vi:** chỉ khi chưa thể di chuyển ngay, bật `--enable-final-field-mutation` cho đúng module cần thiết và lập kế hoạch loại bỏ quyền đó.

Các thư viện thường cần được rà soát gồm JSON/XML mapper, ORM, dependency injection, serializer, mocking framework, công cụ tạo proxy và thư viện kiểm thử. Không kết luận thư viện lỗi thời chỉ vì nó phát cảnh báo; hãy kiểm tra phiên bản hiện tại và tài liệu hỗ trợ JDK 26/27 trước khi quyết định.

Tránh sửa vấn đề bằng cách chuyển sang `sun.misc.Unsafe`, JNI hoặc cơ chế nội bộ khác để ghi final field. Những cách này bỏ qua mục tiêu bảo đảm tính toàn vẹn, tạo phụ thuộc vào implementation và có thể phát sinh rủi ro tương thích hoặc bảo mật khác.

## 11. Quy trình kiểm thử trước khi nâng JDK

1. Chạy ứng dụng và toàn bộ test suite trên JDK 26 với chế độ mặc định để thu thập warning.
2. Chạy lại với `--illegal-final-field-mutation=debug` để lấy stack trace của từng mutation.
3. Dùng JFR event `jdk.FinalFieldMutation` nếu cần phát hiện mutation trong luồng nghiệp vụ dài hoặc khó tái hiện.
4. Nâng cấp hoặc thay thế thư viện thực hiện mutation.
5. Chạy lại với `--illegal-final-field-mutation=deny` để tìm mọi mutation chưa được xử lý.
6. Nếu một thư viện thiết yếu chưa thể di chuyển, bật quyền cho đúng module bằng `--enable-final-field-mutation`, giữ chế độ deny cho các module còn lại.
7. Chạy kiểm thử tích hợp và kiểm thử triển khai bằng đúng JDK, module path, class path và JVM arguments của production.
8. Ghi lại từng ngoại lệ được bật quyền, người sở hữu quyết định và kế hoạch loại bỏ.

Không chỉ kiểm tra unit test. Framework có thể chỉ mutate final field trong một luồng deserialize, proxy hoặc injection được gọi bởi integration test. Cần chạy các đường đi thực tế và kiểm tra recording JFR trước khi kết luận không còn mutation.

## 12. Những hiểu lầm cần tránh

- **Có warning nghĩa là phép ghi đã bị chặn:** sai. Trong chế độ warn mặc định của JDK 26/27, phép ghi vẫn được cho phép nếu các điều kiện khác thỏa mãn.
- **`--add-opens` cho phép ghi final field:** sai. Nó chỉ giải quyết quyền deep reflection; caller còn cần final field mutation được bật.
- **`--enable-final-field-mutation` cho phép ghi mọi final field:** sai. Static final, record field và hidden-class field vẫn không thể sửa theo các mutation method này.
- **Không thấy warning nghĩa là không có mutation:** chưa chắc. Module có thể đã được cấp quyền, ứng dụng có thể không đi qua code path liên quan, hoặc recording chưa bao phủ luồng thực thi.
- **Có thể dùng `--illegal-final-field-mutation=allow` lâu dài:** không nên. Đây là chế độ chuyển tiếp và tùy chọn này dự kiến bị loại bỏ.
- **Final chỉ là quy ước của compiler:** không đúng. Ngữ nghĩa final liên quan đến tính đúng đắn, an toàn khi công bố object và tối ưu hóa của JVM.
- **Chuyển sang Unsafe là cách sửa bền vững:** không. Nó tạo một đường truy cập thấp cấp hơn và không giải quyết nguyên nhân thiết kế.

## 13. Checklist trước khi phát hành

1. Đã chạy trên JDK 26 hoặc JDK 27 để quan sát warning chưa?
2. Đã xác định module, thư viện và call site gây mutation chưa?
3. Đã kiểm tra `Field.set` và `Lookup.unreflectSetter` trong mã hoặc dependency chưa?
4. Đã phân biệt quyền `opens` với quyền `--enable-final-field-mutation` chưa?
5. Đã kiểm tra các final field thuộc record, hidden class hoặc static chưa?
6. Đã thử toàn bộ test suite với `--illegal-final-field-mutation=deny` chưa?
7. Mọi ngoại lệ còn lại có được bật quyền theo đúng module và có chủ sở hữu chưa?
8. Đã loại bỏ các tùy chọn allow/warn khỏi cấu hình dài hạn khi có thể chưa?
9. Đã kiểm thử lại trên đúng runtime và cấu hình triển khai production chưa?

JDK 26 và JDK 27 đang ở giai đoạn cảnh báo để chuẩn bị cho hạn chế mạnh hơn trong tương lai. Cách chuẩn bị đáng tin cậy là tìm ra thư viện đang ghi final field, sửa hoặc nâng cấp thư viện, rồi chạy test ở chế độ deny. Chỉ giữ quyền mutation có chọn lọc cho phụ thuộc thật sự chưa thể di chuyển.

## Tài liệu chính thức

- [JEP 500 — Prepare to Make Final Mean Final](https://openjdk.org/jeps/500): mục tiêu, lộ trình cảnh báo và hạn chế final field mutation.
- [Oracle — Preparing for final Field Mutation Restrictions (JDK 26)](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html): warning mặc định, bốn chế độ xử lý, cấp quyền theo module, stack trace và JFR.
- [Java SE 26 API — Field](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html): điều kiện truy cập và các final field không thể sửa đổi.
- [JDK 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): cú pháp `--enable-final-field-mutation` và `--illegal-final-field-mutation`.
- [Oracle — Significant Changes in JDK 26 Release](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html): xác nhận JDK 26 phát cảnh báo deep reflection mutation.
- [Oracle — Significant Changes in JDK 27 Release](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): xác nhận lộ trình cảnh báo tiếp tục trong JDK 27.
- [Java SE 26 JLS — Subsequent Modification of final Fields](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html): ngữ nghĩa final field và giới hạn của việc thay đổi sau khởi tạo.
- [Oracle — Flight Recorder API Programmer's Guide](https://docs.oracle.com/en/java/javase/26/jfapi/flight-recorder-api-programmers-guide.pdf): cách tạo recording và đọc event bằng công cụ JFR.

Tại ngày 27-11-2026, JDK 26 và JDK 27 đều đang cảnh báo theo lộ trình JEP 500. Tài liệu chính thức mô tả deny mặc định là thay đổi của một bản JDK tương lai, chưa ấn định trong bài này một số release cụ thể.
