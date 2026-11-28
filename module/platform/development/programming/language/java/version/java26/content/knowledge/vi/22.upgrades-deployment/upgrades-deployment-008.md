# Tạo lại AOT cache cho ứng dụng và môi trường đích

AOT cache phải được tạo từ đúng bản ứng dụng và đúng môi trường mà nó sẽ chạy. Với JDK 26, cache gắn với ứng dụng (classpath, JAR hoặc module path), JDK release và hệ điều hành/kiến trúc CPU. Khi một trong các yếu tố đó thay đổi, cần tạo cache mới cho target tương ứng.

Quy trình có ba giai đoạn: **training** chạy ứng dụng với workload đại diện để ghi nhận lớp và thông tin profiling; **assembly** dùng dữ liệu training để tạo file cache; **production** chạy chính bản ứng dụng đó cùng cache. Có thể gộp training và assembly bằng một lệnh, hoặc tách riêng khi cần kiểm soát bộ nhớ và môi trường.

AOT cache là tối ưu của HotSpot JVM nhằm giảm thời gian khởi động và warm-up. Nó không phải native image và không phải preview/incubator feature của Java 26. Các tùy chọn -XX:AOT... là tùy chọn JVM; không cần --enable-preview. JEP 483 đưa AOT class loading/linking vào JDK 24, JEP 514 đơn giản hóa việc tạo cache một bước và JEP 515 bổ sung method profiling ở JDK 25; JDK 26 tiếp tục với JEP 516 để hỗ trợ AOT object caching với mọi garbage collector.

## 1. Xác định target trước khi tạo cache

Một cache không phải artifact dùng chung cho mọi môi trường. Trước khi training, hãy chốt một target cụ thể:

| Thành phần | Phải xác định | Ví dụ |
|---|---|---|
| Ứng dụng | Bản build, entry point, classpath/module path | billing-service build 42 |
| JDK | Feature release sẽ chạy | JDK 26 |
| Hệ điều hành | Nền tảng runtime | Linux |
| Kiến trúc CPU | Instruction set/architecture | x86-64 hoặc AArch64 |
| Bộ thư viện | Danh sách JAR và thứ tự classpath | app.jar, lib-a.jar, lib-b.jar |
| Cấu hình JVM | Các option ảnh hưởng class loading, heap và GC | G1, ZGC, compressed oops |
| Workload training | Luồng khởi động và nghiệp vụ cần cache | khởi tạo service, health check, đọc cấu hình, truy vấn mẫu |

Ví dụ, nếu ứng dụng triển khai trên ba loại node, hãy tạo ba cache độc lập:

~~~text
app-build42-jdk26-linux-x64.aot
app-build42-jdk26-linux-arm64.aot
app-build42-jdk26-windows-x64.aot
~~~

Tên file chỉ giúp con người nhận diện. JVM vẫn kiểm tra tính tương thích thực tế khi nạp cache. Không sao chép cache được tạo trên Windows x64 sang Linux x64, hoặc từ x64 sang ARM64. Nếu target thay JDK release, build ứng dụng hoặc dependency set, tạo cache mới.

Cách an toàn là training và assembly trong container/image gần giống image production của từng target. Với multi-architecture container, chạy pipeline riêng trên runner hoặc môi trường tương thích cho từng kiến trúc.

## 2. Chuẩn bị artifact ứng dụng bất biến

Tạo cache sau khi build đã hoàn tất và dependency đã được khóa phiên bản. Không training trên một bản JAR rồi deploy một bản JAR được build lại, dù source code trông giống nhau.

Trước training, lưu lại:

- Build ID hoặc commit ID.
- Checksum của JAR ứng dụng và từng dependency.
- JDK vendor/build và feature release.
- OS, CPU architecture và container image digest.
- Classpath theo đúng thứ tự.
- Các JVM option liên quan đến class loading, module, heap, GC và compressed oops.
- Cấu hình workload training.

AOT cache cần sự nhất quán giữa training và production:

1. Giữ nguyên timestamp của các JAR qua training, assembly và production.
2. Dùng cùng JDK release và cùng OS/CPU architecture.
3. Dùng classpath dưới dạng danh sách JAR tường minh; tránh thư mục class, wildcard và nested JAR trong classpath của quy trình tạo cache.
4. Classpath production phải là superset của classpath training; tốt nhất giữ nguyên danh sách và thứ tự nếu ứng dụng cho phép.
5. Không dùng JVMTI agent gọi AddToBootstrapClassLoaderSearch hoặc AddToSystemClassLoaderSearch trong quy trình tạo/nạp cache.
6. Không thay đổi các tùy chọn JVM làm biến đổi class loading hoặc module graph giữa training và production mà chưa kiểm tra tương thích.

Ví dụ classpath tường minh trên Linux:

~~~sh
APP_CP="app.jar:lib/library-a.jar:lib/library-b.jar"
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy thay vì dấu hai chấm:

~~~powershell
$APP_CP = "app.jar;lib\library-a.jar;lib\library-b.jar"
~~~

Nếu dùng executable JAR chứa nested JAR, không giả định JVM sẽ xem nested JAR như danh sách classpath thông thường. Hãy dùng layout triển khai được framework hỗ trợ để đưa dependency thành các JAR riêng, rồi tạo cache trên chính layout sẽ chạy production.

## 3. Chọn workload training đại diện

Training ghi nhận các lớp được tải/liên kết và, từ JDK 25, dữ liệu profiling phương thức. Cache có ích khi các luồng training giống những gì ứng dụng thường làm lúc production khởi động và warm-up.

Một workload training cho dịch vụ có thể gồm:

1. Khởi chạy cùng entry point và cấu hình JVM như production.
2. Khởi tạo application context, dependency injection, serializer, client và connection pool.
3. Chạy health check và các request mẫu đi qua handler thường dùng.
4. Thực hiện một số truy vấn đọc hoặc workflow an toàn đại diện cho nghiệp vụ.
5. Chạy qua các nhánh khởi động có tần suất cao, sau đó kết thúc tiến trình có kiểm soát.

Không cần chạy toàn bộ test suite hoặc stress test trong training. Các test framework và nhánh hiếm có thể nạp nhiều lớp không được production dùng, khiến cache lớn mà lợi ích thấp. Nếu cần database, broker hoặc dịch vụ bên ngoài, có thể dùng môi trường staging hoặc dependency giả lập có hành vi đủ gần production; không chạy training trên dữ liệu thật nếu workflow có thể phát sinh giao dịch, gửi email hoặc side effect ngoài ý muốn.

Có hai cách quan sát độ bao phủ:

- Bật class loading log trong một lần chạy khảo sát để biết lớp nào được nạp.
- Dùng Java Flight Recorder với event jdk.ClassLoad và chế độ xem hot methods để xác định lớp/phương thức quan trọng mà training chưa chạm tới.

Nếu workload production thay đổi đáng kể, ví dụ thêm module, plugin hoặc đường khởi động mới, hãy tạo lại cache và cập nhật training scenario.

## 4. Tạo cache một bước bằng AOTCacheOutput

Với ứng dụng có thể chạy training rồi thoát có kiểm soát, cách một bước là ngắn nhất. JDK 26 mặc định AOTMode là auto; khi có AOTCacheOutput, JVM tự chuyển sang record, thu thập dữ liệu và khởi chạy JVM thứ hai để assembly cache khi training JVM kết thúc.

~~~sh
java \
  -XX:AOTCacheOutput=build/aot/app.aot \
  -cp "$APP_CP" \
  com.example.billing.Main \
  --training
~~~

Tham số --training ở ví dụ là cờ riêng của ứng dụng minh họa, không phải tùy chọn JVM. Ứng dụng cần thực hiện workload training và thoát; file cache chỉ được tạo hoàn tất khi tiến trình training kết thúc và bước assembly chạy xong.

Không dùng đồng thời -XX:AOTCacheOutput và -XX:AOTCache trong cùng một lệnh. AOTCacheOutput chỉ định file đầu ra; AOTCache dùng để nạp cache hoặc chỉ định đầu ra trong AOTMode=create.

### 4.1. Lưu ý bộ nhớ của quy trình một bước

JVM thứ hai thực hiện assembly có heap riêng. Nếu training chạy với -Xmx2g, tiến trình assembly cũng có thể dùng heap cùng cỡ; môi trường cần dự trù bộ nhớ cho cả hai tiến trình. Vì vậy, một bước có thể cần xấp xỉ gấp đôi heap đã đặt cho một JVM, chưa tính native memory và tiến trình ứng dụng khác.

Nếu runner nhỏ, training kéo dài hoặc assembly thiếu bộ nhớ, tách ba giai đoạn ở phần tiếp theo. Với quy trình một bước, có thể dùng biến môi trường JDK_AOT_VM_OPTIONS để truyền tùy chọn bổ sung cho JVM assembly thứ hai; chỉ dùng khi cần điều chỉnh tài nguyên và kiểm tra lại bằng đúng JDK đích.

## 5. Tách training và assembly thành hai lệnh

Quy trình tách riêng cho phép chạy training trong môi trường mô phỏng target và chạy assembly trên máy cùng OS/CPU/JDK release nhưng có nhiều RAM hoặc CPU hơn.

### 5.1. Giai đoạn training

~~~sh
java \
  -XX:AOTMode=record \
  -XX:AOTConfiguration=build/aot/app.aotconfig \
  -cp "$APP_CP" \
  com.example.billing.Main \
  --training
~~~

JVM thực thi ứng dụng và ghi quan sát vào file app.aotconfig. Giai đoạn này cần workload đại diện và phải dùng đúng JDK release, OS/CPU architecture cùng artifact ứng dụng của target.

### 5.2. Giai đoạn assembly

~~~sh
java \
  -XX:AOTMode=create \
  -XX:AOTConfiguration=build/aot/app.aotconfig \
  -XX:AOTCache=build/aot/app.aot \
  -cp "$APP_CP"
~~~

JVM đọc file cấu hình training và tạo app.aot. Ở giai đoạn create, ứng dụng không được chạy. Không thêm tên main class hoặc gọi entry point.

File AOTConfiguration và JAR/classpath phải khớp với bản dùng ở training. Assembly có thể chạy trên máy mạnh hơn để có thêm tài nguyên, nhưng vẫn phải cùng JDK release và OS/CPU architecture tương thích với target.

### 5.3. Giai đoạn production

~~~sh
java \
  -XX:AOTCache=build/aot/app.aot \
  -XX:AOTMode=auto \
  -cp "$APP_CP" \
  com.example.billing.Main
~~~

Production nạp cache nếu tương thích. AOTMode=auto là mặc định và cho phép ứng dụng tiếp tục chạy nếu cache không nạp được; khi đó JVM chạy không có AOT cache.

## 6. Tạo cache GC-agnostic khi target dùng collector khác

JDK 26 có JEP 516, mở rộng AOT object caching để dùng được với mọi garbage collector, bao gồm ZGC. JVM có thể lưu object trong định dạng GC-specific/mappable hoặc định dạng GC-agnostic/streamable.

| Định dạng | Cách nạp | Đặc điểm |
|---|---|---|
| GC-specific (mappable) | Ánh xạ dữ liệu object vào vùng nhớ | Có thể rất nhanh ở warm start khi cache đã nằm trong filesystem cache; phụ thuộc biểu diễn object và cấu hình GC liên quan |
| GC-agnostic (streamable) | Đọc object theo luồng và materialize vào heap | Linh hoạt hơn giữa các collector; cần CPU cho quá trình streaming/materialization |

JDK có heuristic lựa chọn định dạng dựa trên môi trường training. Nếu cần chủ động tạo cache dạng streamable, JDK 26 có tùy chọn diagnostic AOTStreamableObjects. Ví dụ khi assembly riêng:

~~~sh
java \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:+AOTStreamableObjects \
  -XX:AOTMode=create \
  -XX:AOTConfiguration=build/aot/app.aotconfig \
  -XX:AOTCache=build/aot/app-streamable.aot \
  -cp "$APP_CP"
~~~

Với quy trình một bước, đặt các tùy chọn này ngay trên lệnh training để JVM chuyển lựa chọn định dạng sang tiến trình assembly:

~~~sh
java \
  -XX:+UnlockDiagnosticVMOptions \
  -XX:+AOTStreamableObjects \
  -XX:AOTCacheOutput=build/aot/app-streamable.aot \
  -cp "$APP_CP" \
  com.example.billing.Main \
  --training
~~~

AOTStreamableObjects tác động đến định dạng object khi ghi cache; không phải tùy chọn phải bật ở mọi lần chạy production. Với quy trình một bước, đặt tùy chọn này ở lệnh training/assembly để nó được chuyển sang JVM assembly. Vì đây là diagnostic option của HotSpot, hãy xác nhận tùy chọn tồn tại trên đúng JDK vendor/build bằng tài liệu và -XX options của runtime đó.

Nếu training dùng G1 nhưng production dùng ZGC, không giả định một cache mappable tạo theo cấu hình cũ tự động phù hợp. Hãy tạo streamable cache khi cần portability giữa collector, sau đó xác minh trên đúng collector production. Nếu không có yêu cầu đổi collector, training với cùng GC và cấu hình heap như production thường đơn giản hơn.

GC-agnostic không đồng nghĩa cache dùng được giữa các OS, CPU architecture, JDK release hoặc bản ứng dụng khác. JEP 516 chỉ giải quyết tính tương thích của định dạng object với garbage collector; các điều kiện target còn lại vẫn phải được giữ nguyên.

## 7. Kiểm tra cache trước khi triển khai

Đừng suy ra cache đã được dùng chỉ vì ứng dụng khởi động thành công. Ở AOTMode=auto, JVM có thể bỏ qua cache rồi tiếp tục chạy.

Trong CI hoặc staging, dùng AOTMode=on để kiểm tra fail-fast:

~~~sh
java \
  -XX:AOTMode=on \
  -XX:AOTCache=build/aot/app.aot \
  -Xlog:aot,class+path=info \
  -cp "$APP_CP" \
  com.example.billing.Main \
  --smoke-test
~~~

Nếu cache không tồn tại hoặc không tương thích, JVM báo lỗi và dừng. Đây là phép kiểm tra trước khi phát hành; không nên dùng mode on làm chế độ production thông thường nếu ứng dụng phải tiếp tục chạy khi cache lỗi.

Tham số --smoke-test trong ví dụ là cờ riêng của ứng dụng, tương tự --training ở phần tạo cache; hãy thay bằng cách chạy smoke workflow mà ứng dụng thực sự hỗ trợ.

Trong production, giữ auto và bật log khi cần điều tra:

~~~sh
java \
  -XX:AOTMode=auto \
  -XX:AOTCache=/opt/app/aot/app.aot \
  -Xlog:aot,class+path=info \
  -cp "$APP_CP" \
  com.example.billing.Main
~~~

Quan sát log để xác nhận cache được nạp và các lớp nào đến từ archive. Nếu cache bị bỏ qua, kiểm tra:

- JDK release và runtime vendor/build.
- OS và CPU architecture.
- Đường dẫn, quyền đọc và checksum file cache.
- Checksum, timestamp và thứ tự JAR trong classpath.
- Các JVM option ảnh hưởng class loading, module graph, heap, compressed oops hoặc GC.
- JVMTI agent và tùy chọn chẩn đoán đang được production sử dụng.

Nếu đã chỉ định AOTMode trên command line, AOTClassLinking được bật tự động trừ khi tắt bằng -XX:-AOTClassLinking. Class linking tăng mức tối ưu nhưng có thêm giới hạn tương thích với một số tùy chọn production. Nếu production có cấu hình class loading đặc biệt, hãy kiểm tra bằng AOTMode=on trước khi quyết định có cần -XX:-AOTClassLinking hay không.

## 8. Tổ chức cache theo target trong CI/CD

Mỗi tổ hợp build/JDK/OS/CPU cần một artifact cache riêng. Pipeline nên dùng cùng application artifact bất biến xuyên suốt training, assembly, kiểm thử và triển khai.

~~~text
Build application and lock dependencies
                 |
                 v
        Select target matrix
       JDK + OS + CPU architecture
                 |
                 v
      Run representative training
       app artifact + target runtime
                 |
                 v
        Assemble target AOT cache
                 |
                 v
      Validate with AOTMode=on
                 |
                 v
   Package app + matching cache + metadata
                 |
                 v
      Deploy with AOTMode=auto
                 |
                 v
       Measure startup and warm-up
~~~

Metadata nên được lưu cạnh cache, ví dụ:

~~~text
buildId: billing-42
jdkRelease: 26
os: linux
architecture: x86_64
applicationSha256: <checksum>
classpathSha256: <checksum-of-ordered-jar-list>
trainingProfile: smoke-startup-v3
collector: G1
cacheFile: app.aot
~~~

Đây là metadata pipeline do nhóm tự quản lý, không phải định dạng bắt buộc của JVM. Không đưa secret, token, private key hoặc dữ liệu nghiệp vụ thật vào metadata training.

Với multi-architecture image, build và publish cache cho từng target. Ví dụ:

| Target | Application artifact | AOT cache |
|---|---|---|
| Linux x86-64 / JDK 26 | billing-42.jar + dependency set | billing-42-jdk26-linux-x64.aot |
| Linux AArch64 / JDK 26 | billing-42.jar + dependency set | billing-42-jdk26-linux-arm64.aot |
| Windows x86-64 / JDK 26 | billing-42.jar + dependency set | billing-42-jdk26-windows-x64.aot |

Không tạo cache trên máy build x64 rồi đưa vào image ARM64 chỉ vì bytecode Java giống nhau. Bytecode có thể chạy đa nền tảng, nhưng AOT cache có ràng buộc nền tảng riêng.

## 9. Rollout, fallback và rollback

Triển khai application và cache như một cặp artifact bất biến. Không cập nhật JAR mà giữ cache của build cũ, cũng không ghi đè cache đang được instance production sử dụng.

Một quy trình rollout an toàn:

1. Tạo cache mới sau khi build và resolve dependency hoàn tất.
2. Xác minh cache trên đúng image/runtime target bằng AOTMode=on.
3. Chạy smoke test và so sánh startup/warm-up với lần chạy không cache.
4. Triển khai canary với AOTMode=auto.
5. Theo dõi log AOT, lỗi khởi động, thời gian ready và warm-up.
6. Mở rộng rollout khi cache được nạp và lợi ích được xác nhận.
7. Khi rollback, quay lại đồng thời application artifact và cache đúng build trước đó.

Nếu cache không nạp được ở production với auto, ứng dụng vẫn có thể chạy mà không có tối ưu AOT. Hãy theo dõi log để phát hiện tình trạng này; fallback không có nghĩa cache đã hoạt động.

Đo startup và warm-up bằng cùng một quy trình đo, cùng cấu hình heap/GC, cùng workload và số lần lặp. Tách cold start khỏi warm start vì filesystem cache có thể làm thay đổi kết quả. Không kết luận hiệu năng chỉ từ một lần chạy.

## 10. Lỗi thường gặp khi tạo cache cho target

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Cache tạo trên máy phát triển nhưng không nạp trong container | OS/CPU, JDK hoặc classpath không khớp | Tạo cache trong image/runner tương thích target |
| Cache không dùng sau khi rebuild JAR | Ứng dụng hoặc dependency đã thay đổi | Tạo cache mới cho build mới |
| Training thành công nhưng warm-up không cải thiện | Workload training bỏ qua đường chạy thường dùng | Bổ sung smoke flow đại diện và method profiling |
| Lệnh một bước hết RAM | JVM assembly thứ hai có heap riêng | Tách training và assembly hoặc tăng tài nguyên assembly |
| AOTMode=on báo không tương thích | Cache sai target, thiếu file hoặc JVM options khác | Kiểm tra -Xlog:aot,class+path=info và tạo lại trên đúng target |
| Cache bị bỏ qua nhưng ứng dụng vẫn chạy | AOTMode=auto fallback | Xem log và xác minh bằng AOTMode=on trong staging |
| Đổi G1 sang ZGC rồi cache object không nạp | Định dạng object cache không phù hợp collector/configuration | Tạo cache streamable bằng JDK 26 và kiểm tra với collector đích |
| Production dùng classpath khác training | Dependency hoặc thứ tự JAR thay đổi | Khóa danh sách JAR và dùng cùng classpath |
| Cache không chứa lớp của tính năng mới | Training không chạy nhánh mới | Cập nhật workload và tạo lại cache |
| Một số option làm mất AOTClassLinking compatibility | Runtime có module/class loading option khác | Kiểm tra các option production; cân nhắc tắt AOTClassLinking nếu phù hợp |
| Triển khai cache chung cho nhiều kiến trúc | Nhầm bytecode portable với cache portable | Tạo artifact cache riêng cho từng OS/CPU target |

## 11. Checklist trước khi phát hành AOT cache

- [ ] Đã chốt build ID, dependency set, JDK release, OS và CPU architecture của target.
- [ ] Training dùng đúng application artifact sẽ triển khai.
- [ ] Classpath là danh sách JAR tường minh, đúng thứ tự và giữ nguyên timestamp.
- [ ] Production classpath tương thích và là superset của training classpath.
- [ ] Workload training bao phủ startup path và luồng thường dùng.
- [ ] Training không phát sinh side effect production ngoài ý muốn.
- [ ] Đã chọn one-step hay three-phase theo tài nguyên của runner.
- [ ] Nếu dùng one-step, đã dự trù heap cho cả training JVM và assembly JVM.
- [ ] Nếu tách giai đoạn, AOTConfiguration được tạo và đọc bằng JDK/OS/CPU tương thích.
- [ ] Nếu đổi collector hoặc cần cache GC-agnostic, đã tạo streamable format và kiểm thử trên collector đích.
- [ ] Đã kiểm tra các JVM option, JVMTI agent và AOTClassLinking constraints.
- [ ] AOTMode=on chạy thành công trong CI/staging.
- [ ] Production dùng AOTMode=auto để có fallback khi cache không nạp được.
- [ ] Log xác nhận cache thực sự được sử dụng.
- [ ] Application và cache được đóng gói, triển khai và rollback cùng nhau.
- [ ] Có cache riêng cho mỗi JDK release và tổ hợp OS/CPU architecture.
- [ ] Đã benchmark cold start, warm start và thời gian warm-up trên workload tương đương.

## Tài liệu tham khảo

- [Java SE 26 — The java Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): phạm vi tương thích của cache, các mode auto/record/create/on, AOTCacheOutput, AOTConfiguration và chẩn đoán.
- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): mô hình AOT cache, training và điều kiện nhất quán giữa training với production.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): tạo cache một bước bằng AOTCacheOutput.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): lưu method profiling trong AOT cache.
- [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): định dạng object cache GC-agnostic trong JDK 26.
- [Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations — Inside Java](https://inside.java/2026/01/09/run-aot-cache/): training workload, classpath, timestamp, tài nguyên assembly và cách kiểm tra cache.
- [JDK 26 Release Notes — Significant Changes](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html): xác nhận cải tiến AOT object caching với mọi garbage collector trong JDK 26.
- [Performance Improvements in JDK 26 — Inside Java](https://inside.java/2026/06/09/jdk-26-performance-improvements/): trade-off giữa cache object mappable và streamable.

