# Lập kế hoạch nâng thư viện và thu hẹp quyền tích hợp bắt buộc

## Mục tiêu

Sau bài học này, bạn có thể:

- Lập danh sách thư viện và thành phần ứng dụng có thể mutate final instance field bằng deep reflection.
- Dùng warning, chế độ debug và JFR để xác định đúng module gọi, field và đường thực thi.
- Đánh giá phiên bản thư viện, thay thế hoặc nâng cấp dependency còn dựa vào final field mutation.
- Xây dựng lộ trình kiểm thử với `--illegal-final-field-mutation=deny`.
- Thu hẹp `--enable-final-field-mutation` vào đúng named module cần ngoại lệ.
- Phân biệt quyền mutate final field với quyền mở package bằng `--add-opens`.
- Quản lý ngoại lệ chuyển tiếp, kiểm tra hồi quy và loại bỏ quyền khi thư viện đã được sửa.

## 1. Vì sao cần một kế hoạch migration?

JEP 500, **Prepare to Make Final Mean Final**, bắt đầu thay đổi hành vi của Java từ JDK 26. Deep reflection có thể từng được dùng để sửa final instance field sau khi object đã khởi tạo. JDK 26 phát warning khi module gọi thực hiện mutation mà chưa được cấp quyền rõ ràng. Mặc định hiện tại là `warn`; một release tương lai dự kiến từ chối mutation không được cấp quyền.

Tác động không chỉ nằm trong mã do nhóm ứng dụng viết. Nhiều framework và thư viện có thể tạo object bằng cách cấp phát trước rồi điền field sau, hoặc dùng reflection để khôi phục trạng thái. Các nhóm thường cần rà soát gồm:

- JSON/XML serializer và deserializer.
- ORM, data mapper và object mapper.
- Dependency injection, proxy và framework tạo object.
- Thư viện kiểm thử, mock, fixture và công cụ instrument.
- Framework phục hồi session, cache hoặc object graph.
- Mã nội bộ dùng `Field.set()` hoặc `MethodHandles.Lookup.unreflectSetter()`.

Mục tiêu migration là loại bỏ các dependency không cần thiết vào final field mutation, sau đó chỉ giữ ngoại lệ có phạm vi nhỏ nhất nếu chưa thể thay thế một thành phần cũ.

## 2. Hiểu đúng hai quyền cần tách riêng

Khi deep reflection muốn mutate một final instance field, cần kiểm tra hai điều kiện độc lập:

1. **Package có được mở cho module gọi hay không?** Deep reflection vào package của module khác cần package đó được mở bằng `opens` hoặc `--add-opens`, theo quy tắc module system.
2. **Module gọi có được phép mutate final field hay không?** JDK 26 dùng `--enable-final-field-mutation` để cấp quyền này.

Ví dụ, một thư viện trong module `legacy.mapper` muốn ghi vào private final field thuộc package `com.example.model` trong module `domain.model`:

~~~bash
java \
  --add-opens=domain.model/com.example.model=legacy.mapper \
  --enable-final-field-mutation=legacy.mapper \
  -m app.main/com.example.Main
~~~

Trong ví dụ:

- `--add-opens` mở đúng package đích cho module gọi.
- `--enable-final-field-mutation` cấp quyền mutate cho module gọi `legacy.mapper`.
- Module khai báo field và module thực hiện mutation có vai trò khác nhau; quyền được cấp cho **caller module**, không phải module sở hữu field.

Nếu package chưa mở, reflection có thể thất bại với lỗi truy cập như `InaccessibleObjectException` trước khi đến bước mutate. Nếu package đã mở nhưng module gọi chưa được cấp quyền, JDK 26 phát warning ở chế độ mặc định; chế độ `deny` từ chối mutation.

Không dùng `--add-opens` như một cách xử lý warning JEP 500. Mở package không cấp quyền mutate final field. Ngược lại, cấp quyền mutate cũng không tự mở package và không vượt qua strong encapsulation.

## 3. Giai đoạn 1: lập inventory và tìm nơi mutation xảy ra

Bắt đầu bằng việc ghi nhận toàn bộ môi trường thực tế:

- JDK vendor, phiên bản và build đang dùng trong production, staging và CI.
- Danh sách dependency trực tiếp và bắc cầu, phiên bản chính xác, module name và JAR thực tế được nạp.
- Framework/plugin thực hiện serialization, mapping, injection, proxy hoặc instrumentation.
- JVM options, module path/class path, `opens` hiện có và các quyền final field mutation đã cấu hình.
- Các đường chạy tạo object quan trọng: khởi động, request, batch, import/export, cache restore, test và shutdown.

Có thể tìm kiếm sơ bộ trong mã nguồn và mã nội bộ các lời gọi đáng chú ý:

~~~java
setAccessible(true)
trySetAccessible()
Field.set(...)
Field.setInt(...)
Lookup.unreflectSetter(...)
~~~

Tìm kiếm tĩnh chỉ là bước định hướng. Framework có thể ẩn thao tác trong dependency đã biên dịch, nên không thể kết luận ứng dụng an toàn chỉ vì không tìm thấy các chuỗi trên trong source code.

Sau inventory tĩnh, chạy ứng dụng bằng JDK 26 với mặc định hoặc đặt rõ:

~~~bash
java --illegal-final-field-mutation=warn -jar app.jar
~~~

Thu thập warning trong các luồng nghiệp vụ đại diện. JDK 26 chỉ phát tối đa một warning cho mỗi module gọi ở chế độ `warn`, vì vậy một warning không có nghĩa chỉ có một field hoặc một call site bị ảnh hưởng.

### Dùng debug để lấy stack trace

Khi cần xác định call site cụ thể, chạy:

~~~bash
java --illegal-final-field-mutation=debug -jar app.jar
~~~

Chế độ `debug` cho phép mutation tiếp tục nhưng phát warning kèm stack trace cho từng lần mutation. Từ stack trace, xác định:

- Module và class thực hiện mutation.
- Class khai báo field và tên field.
- JAR hoặc dependency chứa caller.
- Phiên bản thư viện.
- Đường chạy và dữ liệu khiến thư viện thực hiện thao tác.

Không chỉ lưu nội dung warning. Hãy lưu thêm dependency tree, class loader/module context và cấu hình runtime để có thể tái hiện.

### Dùng JFR để kiểm tra các luồng dài hạn

Java Flight Recorder có event `jdk.FinalFieldMutation` để quan sát final field mutation qua deep reflection và setter MethodHandle được tạo bằng `unreflectSetter(Field)`. Có thể bật recording khi khởi động:

~~~bash
java -XX:StartFlightRecording:filename=final-field-audit.jfr \
     -jar app.jar
~~~

Sau khi chạy các luồng cần kiểm tra, lọc event:

~~~bash
jfr print --events jdk.FinalFieldMutation final-field-audit.jfr
~~~

Dùng JFR để bổ sung bằng chứng khi warning mặc định bị giới hạn một lần cho mỗi module hoặc khi thao tác chỉ xuất hiện ở một luồng ít gặp. Chạy đủ kịch bản nghiệp vụ, vì một recording ngắn không thể chứng minh mọi code path đã được kiểm tra.

## 4. Giai đoạn 2: phân loại mức độ và quyền sở hữu

Sau khi xác định call site, phân loại theo hướng xử lý:

| Nhóm | Ví dụ | Hướng xử lý |
|---|---|---|
| Code do nhóm sở hữu | Helper reflection nội bộ, mapper tự viết | Sửa thiết kế và loại bỏ mutation |
| Dependency có bản mới | Serializer/framework đã hỗ trợ constructor hoặc factory | Nâng cấp và kiểm thử |
| Dependency không còn duy trì | Thư viện cũ không có bản sửa | Thay thế hoặc cô lập |
| Dependency chưa thể thay ngay | Hệ thống cũ phụ thuộc mutation trong một đường chạy quan trọng | Tạo ngoại lệ có phạm vi hẹp, owner và hạn xử lý |
| Mutation không còn được sử dụng | Warning từ test/tool cũ hoặc code path không còn chạy | Xóa dependency/call site và xác nhận bằng test |

Ghi nhận mỗi phát hiện tối thiểu các trường:

- Module gọi và module chứa class khai báo field.
- Class, field và call stack.
- Dependency/JAR và phiên bản.
- Kịch bản tái hiện.
- Mức độ quan trọng của đường chạy.
- Phiên bản thư viện thay thế hoặc issue upstream.
- Người chịu trách nhiệm, trạng thái xử lý và thời điểm cần xóa ngoại lệ.

Đừng cấp quyền cho cả ứng dụng chỉ vì một thư viện gây warning. Cần xác định chính xác module thực hiện mutation và xem có thể nâng cấp, thay thế hoặc cô lập thư viện đó không.

## 5. Giai đoạn 3: nâng cấp hoặc thay thế thư viện

Ưu tiên xử lý theo thứ tự sau:

1. **Nâng cấp lên phiên bản hỗ trợ JDK 26 và không mutate final field.** Đọc release notes, migration guide và issue của thư viện; không suy luận chỉ từ số phiên bản mới hơn.
2. **Chuyển sang API constructor/factory.** Serializer hoặc mapper nên tạo object với đầy đủ trạng thái qua constructor, canonical constructor của record hoặc factory được hỗ trợ.
3. **Thay dependency không còn duy trì.** Chọn thư viện còn hỗ trợ JDK mục tiêu, có chính sách cập nhật bảo mật và không yêu cầu final field mutation.
4. **Cô lập thành phần legacy.** Nếu chưa thể thay ngay, đặt nó sau adapter/module riêng để phạm vi quyền và đường dữ liệu được kiểm soát.
5. **Bỏ cấu hình quyền cũ sau khi cập nhật.** Không để `--enable-final-field-mutation` tồn tại chỉ vì nó đã được thêm trong một đợt sửa lỗi trước.

Khi nâng cấp dependency, kiểm tra cả dependency bắc cầu. Nâng cấp thư viện cấp cao nhưng vẫn kéo theo một phiên bản cũ thực hiện mutation có thể không giải quyết được warning.

Không dùng một cơ chế thấp hơn như `sun.misc.Unsafe` để lách chính sách. Điều đó giữ nguyên vấn đề toàn vẹn và có thể tạo thêm phụ thuộc nội bộ khó bảo trì. `VarHandle` cũng không phải API thay thế để ghi vào final field; final field handle chỉ hỗ trợ các thao tác đọc phù hợp.

## 6. Giai đoạn 4: thu hẹp quyền final field mutation

Nếu sau khi nâng cấp vẫn còn một dependency bắt buộc phải mutate final instance field trong giai đoạn chuyển đổi, hãy cấp quyền cho module gọi cụ thể.

### Trường hợp module path

Ví dụ chỉ module `legacy.mapper` cần quyền:

~~~bash
java \
  --enable-final-field-mutation=legacy.mapper \
  --illegal-final-field-mutation=deny \
  -m app.main/com.example.Main
~~~

Nếu package đích chưa mở, phải cấu hình `opens` riêng. Không thêm toàn bộ module ứng dụng vào danh sách chỉ để tránh một warning.

### Trường hợp class path

Các class trên class path thuộc unnamed module. Tùy chọn:

~~~bash
java --enable-final-field-mutation=ALL-UNNAMED -jar app.jar
~~~

cấp quyền cho tất cả code thuộc unnamed modules, thường bao gồm toàn bộ code trên class path. Đây là ngoại lệ có phạm vi rộng; nó không phân biệt được một JAR legacy với code ứng dụng hoặc các dependency khác.

Nếu chỉ một thư viện trên class path cần quyền, không có cách dùng `ALL-UNNAMED` để giới hạn riêng cho JAR đó. Hãy cân nhắc:

- Chuyển thành phần sang named module nếu hệ sinh thái thư viện hỗ trợ và việc đóng gói cho phép.
- Tách thành phần legacy sang tiến trình/service riêng với giao thức trao đổi dữ liệu rõ ràng.
- Thay thư viện bằng implementation không cần mutate final field.
- Chỉ dùng `ALL-UNNAMED` tạm thời khi đã chấp nhận phạm vi ảnh hưởng và có kế hoạch xóa.

### Chỉ cấp quyền cho module trong boot layer

Danh sách module của `--enable-final-field-mutation` áp dụng cho các module được nạp trong boot layer. Khi lập kế hoạch, xác minh module name thực tế và vị trí nạp của nó. Không giả định module được tạo động ở layer khác sẽ được cấp quyền bằng cùng danh sách.

Quyền mutate là cấu hình do bên vận hành ứng dụng kiểm soát. Thư viện không nên tự yêu cầu hoặc tự bật quyền này cho chính mình. Giữ quyết định cấp quyền ở launcher, service definition hoặc cấu hình triển khai do chủ ứng dụng quản lý.

## 7. Kết hợp deny với allowlist trong giai đoạn chuyển tiếp

Chế độ `deny` rất hữu ích để kiểm tra rằng mọi mutation không có quyền đã được loại bỏ:

~~~bash
java --illegal-final-field-mutation=deny -jar app.jar
~~~

Trong lần kiểm tra đầu tiên, chạy không có `--enable-final-field-mutation`. Điều này giúp phát hiện mọi đường chạy còn phụ thuộc mutation không được cấp quyền.

Nếu một ngoại lệ đã được phê duyệt và cần giữ tạm thời, chạy lại với quyền đúng module:

~~~bash
java \
  --enable-final-field-mutation=legacy.mapper \
  --illegal-final-field-mutation=deny \
  -m app.main/com.example.Main
~~~

Khi đó, module được cấp quyền có thể tiếp tục mutation nếu package đích đã mở; các module còn lại bị từ chối. Cần có hai kết quả test riêng:

- **Không allowlist:** xác nhận ứng dụng và dependency có thể chạy mà không cần final field mutation.
- **Có allowlist tạm thời:** xác nhận ngoại lệ chỉ nằm trong module đã phê duyệt và các module khác vẫn bị deny.

Không xem test `deny` có allowlist là bằng chứng rằng ứng dụng không còn mutation. Allowlist chính là ngoại lệ được phép còn lại.

## 8. Quản lý ngoại lệ như một khoản nợ migration

Mỗi quyền còn giữ lại phải có thông tin quản trị rõ ràng:

| Trường | Nội dung cần ghi |
|---|---|
| Module được cấp quyền | Tên module chính xác hoặc `ALL-UNNAMED` |
| Lý do | Dependency và hành vi cụ thể chưa thể loại bỏ |
| Owner | Nhóm hoặc người chịu trách nhiệm xử lý |
| Phạm vi package mở | Package đích và module được mở |
| Phiên bản dependency | Phiên bản đang dùng và phiên bản dự kiến thay thế |
| Hạn xử lý | Mốc nâng cấp hoặc gỡ ngoại lệ |
| Điều kiện xóa | Test nào phải pass trước khi bỏ quyền |

Không dùng một ngoại lệ không thời hạn. Mỗi lần nâng thư viện hoặc nâng JDK cần rà soát lại danh sách quyền. Khi dependency đã không còn mutation, xóa cả quyền mutate lẫn package opening không còn cần thiết.

Cũng không nên mặc định giữ `--illegal-final-field-mutation=allow` để tránh warning. Chế độ này che khuất phát hiện và làm mất tín hiệu migration.

## 9. Đưa kiểm tra vào CI/CD

Một pipeline phù hợp có thể chia thành các bước:

~~~text
Build dependency graph
          |
          v
Run tests on JDK 26 with warn
          |
          v
Collect warning, debug trace and JFR
          |
          v
Upgrade/replace offending dependencies
          |
          v
Run tests with deny and no allowlist
          |
          +---- failure ---> Identify remaining call sites
          |                         |
          |                         v
          |                  Fix or approve narrow exception
          |                         |
          +<------------------------+
          |
          v
Run tests with approved named-module allowlist
          |
          v
Verify unrelated modules remain denied
          |
          v
Record remaining exceptions and owners
~~~

Gợi ý các job CI:

- **Discovery job:** chạy integration test trên JDK 26 với `warn` hoặc `debug`; lưu log và JFR artifact.
- **Compatibility job:** chạy với `deny` và không allowlist; thất bại nếu còn đường chạy phụ thuộc mutation.
- **Exception job:** nếu có ngoại lệ được phê duyệt, chạy với allowlist tối thiểu và xác nhận module khác không được cấp quyền.
- **Upgrade job:** kiểm tra dependency tree, lockfile và phiên bản framework để tránh kéo lại dependency cũ.
- **Release gate:** yêu cầu owner xác nhận danh sách ngoại lệ, lý do và thời hạn trước khi phát hành.

Không chỉ chạy unit test. Mutation có thể xảy ra khi deserialize dữ liệu thực, khôi phục session, xử lý request hoặc chạy test integration. Cần bao phủ các đường code đó.

## 10. Xử lý rollback và sự cố triển khai

Nếu sau khi bật `deny` một luồng production thất bại:

1. Lấy exception và stack trace để xác định module/call site.
2. So sánh dependency tree và JVM flags giữa bản phát hành mới và bản trước.
3. Xác định package có được mở đúng hay lỗi là do thiếu quyền mutate.
4. Kiểm tra thư viện có bản vá tương thích hay không.
5. Nếu cần khôi phục dịch vụ, rollback phiên bản ứng dụng hoặc dùng ngoại lệ tạm thời đã được đánh giá, giới hạn ở đúng module.
6. Tạo issue có owner và hạn gỡ quyền; giữ lại log để không mất nguyên nhân gốc.

Không thêm `ALL-UNNAMED` vào production như phản xạ đầu tiên khi gặp `IllegalAccessException`. Nó có thể làm ứng dụng chạy lại nhưng đồng thời trao quyền rộng cho mọi code class path. Nếu cần biện pháp tạm thời, ưu tiên module hóa hoặc cô lập dependency để giới hạn phạm vi.

## 11. Những thay đổi cần kiểm tra khi nâng JDK

JDK 26 triển khai JEP 500 với chế độ mặc định `warn`. Các chế độ chuyển tiếp của `--illegal-final-field-mutation` gồm:

| Chế độ | Hành vi |
|---|---|
| `allow` | Cho phép mutation không cảnh báo |
| `warn` | Cho phép và cảnh báo tối đa một lần cho mỗi module gọi |
| `debug` | Cho phép, cảnh báo và in stack trace cho từng mutation |
| `deny` | Từ chối mutation không được cấp quyền |

Trong release tương lai, mặc định sẽ nghiêm ngặt hơn và mutation không có quyền tường minh sẽ bị từ chối. Không gắn kế hoạch vào một số phiên bản cụ thể nếu JEP hoặc release note chưa xác nhận mốc đó; thay vào đó, dùng test `deny` ngay trong pipeline để chủ động phát hiện.

JEP 500 là thay đổi hành vi runtime, không phải preview feature. Không cần `--enable-preview` để dùng các chế độ trên. Các cờ chuyển tiếp không nên được coi là API cấu hình lâu dài; mục tiêu là xóa nhu cầu mutation, không phải giữ cờ mãi mãi.

## 12. Checklist hoàn tất migration

- [ ] Đã ghi lại JDK vendor/build và toàn bộ dependency thực tế.
- [ ] Đã chạy các luồng đại diện trên JDK 26 với `warn`.
- [ ] Đã dùng `debug` hoặc JFR để xác định call site còn mutation.
- [ ] Đã phân loại code nội bộ và dependency bên ngoài.
- [ ] Đã nâng cấp hoặc thay thế thư viện có bản sửa.
- [ ] Đã loại bỏ các call site do ứng dụng sở hữu.
- [ ] Đã thử `deny` không allowlist trong CI.
- [ ] Mọi ngoại lệ còn lại có module owner, lý do và thời hạn.
- [ ] Không dùng `ALL-UNNAMED` nếu có thể giới hạn vào named module.
- [ ] `--add-opens` chỉ mở package cần thiết cho đúng caller module.
- [ ] Đã xác nhận module được cấp quyền nằm trong boot layer.
- [ ] Đã kiểm tra các đường serialization, ORM, injection, test và khôi phục dữ liệu.
- [ ] Đã xóa quyền và package opening sau khi dependency được sửa.
- [ ] Có kế hoạch kiểm tra lại khi nâng lên JDK tiếp theo.

## Kết luận

Migration theo JEP 500 nên bắt đầu bằng việc quan sát mutation trên JDK 26, xác định module và dependency chịu trách nhiệm, sau đó nâng cấp hoặc thay thế thư viện. Chế độ `deny` không allowlist là phép kiểm tra quan trọng để chứng minh các đường chạy không còn phụ thuộc vào mutation trái phép. Nếu còn ngoại lệ, chỉ cấp quyền cho named module thực sự cần, mở đúng package cho caller và quản lý ngoại lệ với owner cùng hạn xử lý. Tránh `ALL-UNNAMED` nếu có thể cô lập dependency, và xóa toàn bộ quyền chuyển tiếp khi thư viện đã tương thích.

## Tài liệu tham khảo

- [JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500)
- [Oracle JDK 26 Migration Guide – Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
- [Java SE 26 API – Mutation methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html)
- [Java 26 java Command – --enable-final-field-mutation and --illegal-final-field-mutation](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Inside Java – Avoiding Final Field Mutation](https://inside.java/2026/04/27/avoiding-final-field-mutation/)
- [Inside Java – JEP 500 Quality Outreach Heads-up](https://inside.java/2026/05/15/quality-heads-up/)
