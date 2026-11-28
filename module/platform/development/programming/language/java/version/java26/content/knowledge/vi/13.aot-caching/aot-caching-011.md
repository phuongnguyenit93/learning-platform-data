# Tạo lại khi mã, dependency hoặc môi trường không còn tương thích

AOT cache chỉ có giá trị khi nó được tạo từ đúng phiên bản ứng dụng và môi trường chạy tương thích. Khi mã ứng dụng được build lại, thư viện phụ thuộc thay đổi, JDK được nâng cấp hoặc nền tảng triển khai chuyển sang hệ điều hành/kiến trúc CPU khác, cần tạo lại cache. Dùng cache cũ có thể khiến JVM từ chối nạp cache; trong một số trường hợp, cấu hình chẩn đoán hoặc agent còn làm thay đổi điều kiện tương thích.

AOT cache là tối ưu của HotSpot JVM nhằm giảm thời gian khởi động và warm-up. Nó lưu các artifact được chuẩn bị trước, như lớp đã tải/liên kết, đối tượng JDK được cache và thông tin profiling phương thức trong các JDK có hỗ trợ. Đây không phải native image: ứng dụng vẫn chạy trên JVM và JIT vẫn tiếp tục tối ưu trong runtime.

Bài học này tập trung vào việc xác định cache đã lỗi thời hay chưa, phân biệt thay đổi bắt buộc phải tạo lại với thay đổi chỉ làm workload training kém đại diện, và xây dựng quy trình phát hành cache đi cùng đúng build ứng dụng.

AOT cache là tính năng của HotSpot JVM, không phải preview hoặc incubator API của Java SE; không cần bật --enable-preview. Các tùy chọn -XX dùng để tạo và nạp cache là tùy chọn riêng của HotSpot, vì vậy cần kiểm tra tài liệu của đúng JVM đang triển khai. JEP 483 giới thiệu AOT class loading/linking trong JDK 24, JEP 515 bổ sung method profiling trong JDK 25, còn JEP 516 mở rộng object caching để dùng được với mọi GC trong JDK 26.

## 1. AOT cache phụ thuộc vào những gì?

Theo tài liệu lệnh java của JDK 26, AOT cache gắn với ba yếu tố chính:

1. **Ứng dụng** được xác định qua classpath, JAR hoặc module path.
2. **JDK release** dùng để tạo và nạp cache.
3. **Hệ điều hành và kiến trúc CPU** của nền tảng.

Nếu một trong các yếu tố này thay đổi, phải tạo lại AOT cache. Ngoài ra, một số tùy chọn JVM không tương thích cũng có thể khiến cache không được nạp, ví dụ một số JVMTI agent can thiệp vào class loading.

| Thay đổi | Ảnh hưởng | Hành động |
|---|---|---|
| Sửa mã nguồn rồi đóng gói lại JAR | Nội dung class của ứng dụng thay đổi | Tạo lại cache cho build mới |
| Thêm, xóa, thay phiên bản hoặc đổi thứ tự JAR phụ thuộc | Classpath và tập lớp có thể được cache thay đổi | Tạo lại cache |
| Đổi JDK release, ví dụ JDK 26 sang JDK 27 | Cache gắn với JDK release đã tạo nó | Tạo lại bằng JDK đích |
| Đổi hệ điều hành hoặc kiến trúc CPU, ví dụ Linux x64 sang Windows ARM64 | Nền tảng cache không còn tương thích | Tạo lại trên nền tảng đích |
| Thêm agent hoặc tùy chọn JVM có thể sửa/biến đổi lớp | Có thể vi phạm điều kiện training và production | Kiểm tra log; tạo lại cache với cấu hình runtime phù hợp |
| Chỉ đổi biến môi trường không ảnh hưởng classpath/JDK/nền tảng | Không tự động làm cache sai định dạng, nhưng có thể đổi đường chạy ứng dụng | Đánh giá lại training coverage; tạo lại nếu luồng khởi động/hot path thay đổi đáng kể |
| Đổi garbage collector trên JDK 26 | JEP 516 bổ sung định dạng object GC-agnostic, nhưng cache cũng có thể dùng định dạng memory-mapped phụ thuộc GC | Kiểm tra định dạng cache; nếu cần dùng giữa các GC, tạo cache dạng streamable hoặc tạo lại trên collector đích |

Quy tắc an toàn cho pipeline là gắn cache với một build cụ thể và không tái sử dụng sau khi build hoặc dependency set đã thay đổi. Nếu chưa chắc một thay đổi có làm mất tương thích hay không, tạo lại cache thường ít rủi ro hơn việc phát hành cache cũ.

## 2. Phân biệt cache không tương thích với training không còn đại diện

Hai tình huống này có thể cho biểu hiện khác nhau:

- **Không tương thích**: JVM không thể nạp cache vì ứng dụng, JDK, OS/CPU hoặc tùy chọn runtime không khớp. Cache cần được tạo lại theo môi trường mới.
- **Training không còn đại diện**: cache vẫn nạp được, nhưng quá trình training không đi qua các lớp hoặc phương thức mà phiên bản ứng dụng hiện tại thường sử dụng. Ứng dụng vẫn chạy, nhưng lợi ích khởi động/warm-up có thể thấp hơn.

Ví dụ, một bản build mới thêm tính năng xuất báo cáo. Nếu training không chạy luồng xuất báo cáo, cache có thể không chứa các lớp được nạp riêng cho luồng đó. Đây chủ yếu là vấn đề độ bao phủ của training. Tuy nhiên, vì mã và dependency đã thay đổi, cache vẫn nên được tạo lại cho build mới.

Một thay đổi cấu hình cũng cần được đánh giá theo hai góc độ. Đổi URL dịch vụ bên ngoài thường không làm classpath thay đổi. Nhưng nếu cấu hình mới kích hoạt một module hoặc plugin làm nạp thêm lớp trong lúc khởi động, training nên chạy với cấu hình gần production để cache bao phủ đúng đường chạy.

## 3. Tạo cache sau mỗi build ứng dụng

JEP 514 trong JDK 25 đã đơn giản hóa việc tạo AOT cache bằng tùy chọn -XX:AOTCacheOutput. Trong JDK 26, cách dùng một lệnh vẫn áp dụng:

~~~sh
# Training run và assembly trong một quy trình
java -XX:AOTCacheOutput=app.aot -jar app.jar
~~~

JVM chạy ứng dụng để thu thập thông tin training, sau đó khởi chạy JVM thứ hai để tạo file app.aot khi tiến trình training kết thúc. Trong JDK 26, AOTMode mặc định là auto; khi có AOTCacheOutput, JVM tự chuyển sang chế độ record và thực hiện bước assembly tiếp theo.

File cache được ghi khi training JVM kết thúc. Với dịch vụ chạy liên tục, cần có cách kết thúc phiên training có kiểm soát sau khi đã chạy đủ workflow đại diện; nếu tiến trình không thoát, bước tạo cache cũng chưa hoàn tất.

Khi triển khai cùng build:

~~~sh
# Production run
java -XX:AOTCache=app.aot -jar app.jar
~~~

Không dùng lại app.aot sau khi thay app.jar hoặc dependency. Hãy tạo cache mới trong pipeline sau khi đã hoàn tất build, đóng gói dependency và xác định JDK/nền tảng đích.

Với ứng dụng dùng classpath thay vì executable JAR, phải dùng cùng danh sách JAR theo đúng thứ tự ở training và production. Tránh đưa thư mục class, wildcard hoặc nested JAR vào classpath của quy trình tạo cache. Bảo toàn timestamp của JAR giữa training và production; một số framework và quy trình đóng gói dựa vào điều kiện này để nhận diện đúng artifact.

## 4. Tách training và assembly khi môi trường ít RAM

Lệnh một bước thuận tiện, nhưng JVM thứ hai thực hiện assembly có heap riêng. Trong môi trường giới hạn bộ nhớ, tổng nhu cầu heap của training và assembly có thể xấp xỉ gấp đôi heap đã cấu hình cho mỗi tiến trình.

Có thể tách thành ba giai đoạn để chạy training và assembly ở hai môi trường khác nhau:

### 4.1. Giai đoạn training

~~~sh
java \
  -XX:AOTMode=record \
  -XX:AOTConfiguration=app.aotconfig \
  -cp app.jar \
  com.example.Main
~~~

Ứng dụng chạy với workload đại diện. JVM ghi thông tin vào app.aotconfig. Giai đoạn này thực thi ứng dụng thật, vì vậy cần dùng môi trường test/staging có dữ liệu và dịch vụ phụ trợ phù hợp.

### 4.2. Giai đoạn assembly

~~~sh
java \
  -XX:AOTMode=create \
  -XX:AOTConfiguration=app.aotconfig \
  -XX:AOTCache=app.aot \
  -cp app.jar
~~~

JVM đọc cấu hình training và tạo app.aot. Ứng dụng không được chạy lại trong giai đoạn assembly. Dùng JDK release, OS/CPU và artifact ứng dụng tương thích với giai đoạn training.

### 4.3. Giai đoạn production

~~~sh
java \
  -XX:AOTCache=app.aot \
  -cp app.jar \
  com.example.Main
~~~

Production dùng cache đã tạo cùng ứng dụng. Có thể giữ file cấu hình và cache trong artifact pipeline để truy nguyên chúng thuộc build nào.

Với JDK 26, -XX:AOTCache có thể được dùng ở chế độ create để chỉ định file cache đầu ra. Đây là cú pháp của AOT mode hiện hành; không sao chép lệnh từ hướng dẫn JDK cũ mà chưa đối chiếu man page của JDK đích.

## 5. Chọn workload training phù hợp

Cache chỉ ghi nhận những gì JVM quan sát được trong quá trình training. Một lần khởi động quá ngắn có thể bỏ qua các luồng quan trọng; một bộ test quá rộng lại có thể nạp nhiều lớp không được dùng trong production và làm cache lớn hơn cần thiết.

Một quy trình training tốt nên:

- Chạy cùng phiên bản ứng dụng và dependency sẽ phát hành.
- Dùng cùng JDK release và cùng OS/CPU architecture với production.
- Thực hiện các đường khởi động thường dùng, như tạo application context, khởi tạo singleton, đăng ký handler và tải cấu hình.
- Chạy một phần workflow production-like để method profiling có dữ liệu hữu ích.
- Tránh chạy test framework nặng hoặc các nhánh hiếm không có trong workload thực.
- Không dùng mock làm thay đổi cấu trúc class loading theo cách khác xa production.
- Dùng cùng classpath, cùng thứ tự JAR và bảo toàn timestamp của JAR.

Từ JDK 25, JEP 515 bổ sung method profiling vào AOT cache. Vì vậy, training không chỉ ảnh hưởng lớp nào được nạp sẵn mà còn ảnh hưởng thông tin về phương thức thường được gọi. Training thiếu luồng nghiệp vụ chính có thể làm giảm lợi ích warm-up dù cache vẫn nạp thành công.

Nếu ứng dụng có nhiều chế độ khởi động, hãy tạo một tập training đại diện cho các chế độ production quan trọng. Không cần cố nạp mọi lớp trong toàn bộ test suite; mục tiêu là cache gọn và phản ánh đúng workload sẽ chạy.

## 6. Khi nào thay đổi môi trường buộc phải tạo lại?

### 6.1. Nâng cấp JDK

AOT cache được tạo cho một JDK release cụ thể. Khi chuyển từ JDK 26 sang JDK 27, phải tạo lại cache bằng JDK 27. Không dùng file cache tạo bởi JDK 26 để nạp vào JDK 27.

Trong pipeline, nên tạo cache sau khi đã chọn chính xác JDK runtime sẽ được triển khai. Nếu đổi vendor hoặc build JDK trong khi vẫn cùng feature release, hãy tạo lại và kiểm thử bằng chính runtime cuối cùng để tránh phụ thuộc vào khác biệt implementation.

### 6.2. Thay đổi mã và dependency

Các trường hợp cần tạo lại:

- Compile lại class ứng dụng.
- Thay executable JAR.
- Thêm hoặc bỏ dependency.
- Nâng phiên bản framework, thư viện logging, driver hoặc module.
- Đổi thứ tự classpath.
- Thay nội dung JAR dù tên file vẫn giữ nguyên.

Một file cache cũ có thể không còn khớp với tập lớp hoặc metadata mà JVM thấy ở runtime. Hãy coi mỗi build bất biến là một đơn vị phát hành có cache riêng.

### 6.3. Thay đổi OS hoặc CPU architecture

Không chuyển cache giữa các nền tảng như Linux x64, Windows x64 và Linux AArch64. Tạo cache trên đúng nền tảng triển khai hoặc trên một môi trường build tương thích với nền tảng đích.

Nếu hệ thống phát hành nhiều kiến trúc, duy trì cache riêng cho từng tổ hợp OS/CPU architecture. Không đặt một file cache dùng chung cho mọi image/container nếu chúng chạy trên nền tảng khác nhau.

### 6.4. Thay đổi garbage collector trong JDK 26

Trước JDK 26, object caching trong AOT cache dùng định dạng bộ nhớ phụ thuộc collector; điều này hạn chế việc dùng các object đã cache với ZGC. JEP 516 bổ sung định dạng GC-agnostic (streamable): JVM đọc object theo luồng và materialize chúng vào heap theo cách phù hợp với collector đang chạy. Nhờ đó JDK 26 hỗ trợ AOT object caching với mọi GC, bao gồm G1, Parallel GC, Serial GC và ZGC.

Tuy nhiên, cần phân biệt hai dạng cache object:

- **GC-specific / memory-mapped**: có thể khởi động rất nhanh khi cache đã nằm trong filesystem cache, nhưng phụ thuộc cách collector biểu diễn object và reference.
- **GC-agnostic / streamable**: linh hoạt giữa các collector; JVM nạp object tuần tự và có thể dùng thêm CPU để materialize object.

Nếu training và production dùng collector khác nhau, không mặc định rằng cache memory-mapped tạo theo collector cũ có thể dùng nguyên trạng. Khi cần portability giữa GC, tạo cache bằng định dạng streamable với tùy chọn HotSpot JDK 26:

~~~sh
java \
  -XX:AOTMode=create \
  -XX:AOTConfiguration=app.aotconfig \
  -XX:AOTCache=app.aot \
  -XX:+AOTStreamableObjects \
  -cp app.jar
~~~

Sau đó kiểm tra trên collector đích bằng AOTMode=on và đo lại startup/warm-up. Nếu không cần chia sẻ cache giữa các collector, định dạng memory-mapped mặc định có thể phù hợp hơn cho warm start; hãy chọn theo môi trường thực tế và số liệu benchmark.

## 7. Tùy chọn JVM có thể làm cache không được nạp

AOT cache không tương thích với mọi tổ hợp JVM option. Một số JVMTI agent có thể thêm hoặc thay đổi lớp trong quá trình khởi động; các tùy chọn như AOTClassLinking cũng có điều kiện sử dụng riêng. Khi chỉ định AOTMode trên command line, AOTClassLinking được bật tự động trừ khi tắt rõ ràng bằng -XX:-AOTClassLinking; cache được tạo với class linking có thể bị giới hạn bởi một số tùy chọn production. Ngoài ra, không truyền đồng thời -XX:AOTCache và -XX:AOTCacheOutput trong cùng lệnh.

Nếu ứng dụng chạy production với agent hoặc tùy chọn chẩn đoán khác training, hãy kiểm tra khả năng tương thích. Không mặc định rằng chỉ cần cùng JAR là cache sẽ được nạp.

Để kiểm tra nghiêm ngặt, chạy:

~~~sh
java \
  -XX:AOTCache=app.aot \
  -XX:AOTMode=on \
  -Xlog:aot \
  -jar app.jar
~~~

AOTMode=on yêu cầu JVM nạp cache; nếu cache không tồn tại hoặc không tương thích, JVM báo lỗi và dừng. Đây là cách kiểm tra trong CI/staging hoặc khi debug.

Với production, nên dùng chế độ auto mặc định:

~~~sh
java \
  -XX:AOTCache=app.aot \
  -XX:AOTMode=auto \
  -Xlog:aot,class+path=info \
  -jar app.jar
~~~

Nếu cache không nạp được, auto cho phép ứng dụng tiếp tục chạy mà không dùng cache. Đây là chế độ phù hợp hơn khi cần ưu tiên tính sẵn sàng; log giúp xác định cache đã được dùng hay bị bỏ qua.

Không dùng AOTMode=on như cấu hình production thông thường nếu yêu cầu ứng dụng phải tiếp tục chạy khi cache lỗi. Dùng nó như một phép kiểm tra fail-fast trước khi phát hành.

## 8. Xác minh cache đã được sử dụng

Một ứng dụng khởi động thành công không có nghĩa AOT cache đã được nạp. Ở chế độ auto, JVM có thể bỏ qua cache và vẫn chạy bình thường.

Bật log:

~~~sh
java \
  -XX:AOTCache=app.aot \
  -Xlog:aot,class+path=info \
  -jar app.jar
~~~

Quan sát thông báo AOT và nguồn class loading. Các lớp được lấy từ shared objects file cho biết JVM đang sử dụng dữ liệu đã lưu trong archive/cache. Nếu log báo cache bị bỏ qua, hãy kiểm tra:

- JDK release và vendor/build.
- OS/CPU architecture.
- Đường dẫn, quyền đọc và tính toàn vẹn của file .aot.
- Classpath hoặc module path và thứ tự JAR.
- Timestamp của JAR.
- JVM options, JVMTI agents và cấu hình AOTClassLinking.
- Ứng dụng có được build lại sau lần training hay không.

Có thể so sánh startup time qua nhiều lần chạy nóng/lạnh, nhưng phải giữ điều kiện hệ thống tương đương. Một cache được nạp thành công vẫn có thể không cải thiện nếu training không đại diện hoặc startup bị giới hạn bởi I/O, network hay khởi tạo dịch vụ bên ngoài.

## 9. Lập quy tắc cache theo build trong CI/CD

Một pipeline dễ truy nguyên nên tạo cache như một artifact gắn với build:

~~~text
Build application
      |
      v
Resolve dependency set
      |
      v
Select JDK + OS/CPU target
      |
      v
Run representative training
      |
      v
Assemble AOT cache
      |
      v
Validate with AOTMode=on
      |
      v
Publish application + matching cache
      |
      v
Deploy with AOTMode=auto
~~~

Tên file cache nên thể hiện build và nền tảng, ví dụ:

~~~text
app-2026.11.27-build42-jdk26-linux-x64.aot
app-2026.11.27-build42-jdk26-linux-arm64.aot
~~~

Không ghi đè một cache đang được phiên bản production sử dụng. Tạo artifact mới, kiểm tra cache cùng application package, sau đó triển khai chúng như một cặp. Khi rollback ứng dụng, rollback đúng cache được tạo cho build đó.

Trong pipeline, có thể lưu kèm metadata phát hành bên ngoài file cache: commit/build ID, checksum JAR, danh sách dependency theo thứ tự, JDK vendor/version, OS và kiến trúc CPU. Metadata này giúp xác định nhanh nguyên nhân cache lỗi thời mà không phải suy luận từ tên file.

## 10. Lưu ý khi dùng Spring Boot và executable JAR lồng nhau

Một số executable JAR dùng nested JAR và custom class loader. AOT cache yêu cầu classpath phù hợp; vì vậy không nên giả định mọi cách chạy executable JAR đều tạo được cache hiệu quả.

Với Spring Boot, tài liệu hiện hành khuyến nghị dùng chế độ extract application để đưa dependency thành danh sách JAR thông thường. Khi tạo cache, training và production phải dùng cùng layout và classpath. Nếu dùng classpath superset, các JAR thêm vào cuối có thể chạy nhưng không được cache; khi dependency set của ứng dụng thay đổi, nên tạo cache mới để bảo đảm kết quả có thể tái lập.

Ví dụ minh họa quy trình Spring Boot phụ thuộc vào chế độ extract và phiên bản Spring Boot:

~~~sh
java -Djarmode=tools -jar application.jar extract --destination application
cd application
java -XX:AOTCacheOutput=app.aot -Dspring.context.exit=onRefresh -jar application.jar
~~~

Tùy chọn spring.context.exit=onRefresh chỉ phù hợp khi mục tiêu training là khởi tạo ApplicationContext rồi thoát. Nếu cần method profile và startup path sát production hơn, hãy chạy thêm workflow đại diện thay vì chỉ dừng ngay sau khi context refresh.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| JVM không nạp cache sau khi deploy build mới | Cache được tạo từ mã hoặc JAR cũ | Tạo lại sau mỗi build phát hành |
| Cache lỗi sau khi nâng JDK | Cache gắn với JDK release cũ | Training và assembly bằng JDK đích |
| Cache không dùng được trên máy khác | OS hoặc CPU architecture khác | Tạo cache riêng cho nền tảng đích |
| Cache không nạp sau khi đổi dependency | Classpath, thứ tự hoặc timestamp JAR thay đổi | Dùng danh sách JAR ổn định và tạo cache mới |
| Cache tạo được nhưng ít cải thiện warm-up | Training không chạy các luồng nghiệp vụ quan trọng | Bổ sung workload đại diện và method profiling |
| Một bước tạo cache bị thiếu RAM | JVM assembly chạy thêm tiến trình có heap riêng | Tách training và assembly thành ba giai đoạn |
| Production chạy được nhưng cache bị bỏ qua | AOTMode=auto fallback khi cache không tương thích | Xem -Xlog:aot,class+path=info và kiểm tra trong staging bằng AOTMode=on |
| Đổi G1 sang ZGC rồi cache bị nghi ngờ | Áp dụng giả định cũ trước JDK 26 | Kiểm tra JEP 516; JDK 26 hỗ trợ AOT object caching với mọi GC |
| Spring Boot không cache được nhiều lớp | Nested JAR/custom class loader hoặc classpath không phù hợp | Dùng extracted application và giữ classpath giống training |
| Training tạo cache quá lớn | Nạp nhiều lớp không dùng trong production | Thu hẹp workload training và bỏ test framework không cần thiết |

## 12. Checklist trước khi phát hành cache

- [ ] Cache được tạo từ đúng build ứng dụng sẽ triển khai.
- [ ] Dependency set, classpath/module path và thứ tự JAR khớp với training.
- [ ] Timestamp của JAR được giữ nguyên qua training và production.
- [ ] Training và production dùng cùng JDK release.
- [ ] Training và production dùng cùng OS/CPU architecture.
- [ ] Workload training đại diện cho đường khởi động và workflow thường dùng.
- [ ] Đã tạo cache mới sau khi sửa mã hoặc cập nhật dependency.
- [ ] Đã kiểm tra các JVM option và JVMTI agent có thể làm cache không tương thích.
- [ ] Đã kiểm tra bằng AOTMode=on trong CI/staging.
- [ ] Production dùng AOTMode=auto để tiếp tục chạy nếu cache không nạp được.
- [ ] Log -Xlog:aot,class+path=info xác nhận cache thực sự được sử dụng.
- [ ] Artifact application và .aot được phát hành/rollback cùng nhau.
- [ ] Có cache riêng cho từng OS/CPU architecture.
- [ ] Đã benchmark startup và warm-up trước khi kết luận cache có lợi.

## Tài liệu tham khảo

- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache, ba giai đoạn training/assembly/production và điều kiện tương thích.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): tạo cache bằng một lệnh với AOTCacheOutput.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): đưa thông tin profiling phương thức vào AOT cache.
- [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): hỗ trợ AOT object caching với mọi garbage collector từ JDK 26.
- [JDK 26 java command — Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): các tùy chọn AOTCache, AOTCacheOutput, AOTConfiguration, AOTMode và hành vi khi cache không tương thích.
- [Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): consistency giữa training và production, dependency, JDK, nền tảng và cách kiểm tra cache.
- [Performance Improvements in JDK 26](https://inside.java/2026/06/09/jdk-26-performance-improvements/): cải tiến AOT object caching và lựa chọn GC.
- [Spring Framework — JVM AOT Cache](https://docs.spring.io/spring/reference/7.0/integration/aot-cache.html): cách dùng cache với extracted application và yêu cầu classpath.

