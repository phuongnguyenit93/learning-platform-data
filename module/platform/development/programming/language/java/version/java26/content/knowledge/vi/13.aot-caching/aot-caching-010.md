# Phân biệt độc lập GC với phụ thuộc ứng dụng, JDK, OS và CPU

*Tình trạng được đối chiếu với JDK 26 tại ngày 27/11/2026.*

JEP 516 – **Ahead-of-Time Object Caching with Any GC** giúp AOT cache của HotSpot sử dụng được với mọi garbage collector (GC), kể cả ZGC. Tuy nhiên, “độc lập GC” chỉ mô tả định dạng lưu object mới của AOT cache. Nó **không** biến file `.aot` thành artifact dùng chung cho mọi ứng dụng, mọi JDK hoặc mọi hệ điều hành và CPU.

Theo tài liệu JDK 26, một AOT cache gắn với ba thành phần:

1. **Ứng dụng cụ thể**, được xác định qua `-classpath`, `-jar` hoặc `--module-path`.
2. **Một JDK release cụ thể**.
3. **Một hệ điều hành và CPU architecture cụ thể**.

Nếu một trong ba thành phần này thay đổi, phải tạo lại cache. JEP 516 chỉ loại bỏ phụ thuộc GC khi phần object của cache được tạo ở định dạng **GC-agnostic/streamable**. Nếu object vẫn ở định dạng **GC-specific/memory-mappable**, cache tiếp tục phụ thuộc cách GC biểu diễn object và reference.

## 1. Tách bốn chiều tương thích

Khi thiết kế pipeline AOT, hãy xem khả năng dùng lại cache theo bốn chiều riêng:

| Chiều | JDK 26 yêu cầu | JEP 516 thay đổi gì? |
|---|---|---|
| GC | Có thể dùng G1, Parallel, Serial, Shenandoah, ZGC nếu object archive ở dạng GC-agnostic | Mở rộng khả năng dùng cache qua các GC |
| Ứng dụng | Phải đúng ứng dụng và classpath/JAR/module path đã dùng để tạo cache | Không thay đổi |
| JDK | Phải đúng JDK release đã tạo cache | Không thay đổi |
| OS và CPU architecture | Phải đúng nền tảng hệ điều hành và kiến trúc CPU | Không thay đổi |

Có thể ghi nhớ bằng câu sau: **đổi GC có thể vẫn dùng lại cache streamable; đổi ứng dụng, JDK release, OS hoặc CPU architecture thì tạo cache mới.**

Không nên dùng cụm “AOT cache portable” mà không nêu rõ portable theo chiều nào. JEP 516 làm định dạng object độc lập với GC; nó không tạo một định dạng cache đa nền tảng hay đa phiên bản JDK.

## 2. Vì sao JEP 516 chỉ cần giải quyết chiều GC?

Object trong heap có header, reference và cách bố trí bộ nhớ do JVM/GC quản lý. Các GC có thể dùng cách biểu diễn reference khác nhau. Ví dụ, compressed oops có thể dùng reference 32-bit trong một số cấu hình heap, trong khi ZGC cần cách biểu diễn reference có metadata riêng.

Định dạng memory-mappable cũ cho phép JVM ánh xạ trực tiếp object đã lưu vào heap. Điều này nhanh khi file cache đã nằm trong filesystem page cache, nhưng các byte của object phải tương thích với cách heap hiện tại biểu diễn object và reference.

JEP 516 bổ sung định dạng **streamable**. Thay vì phụ thuộc địa chỉ hoặc cách mã hóa reference của heap lúc training, dữ liệu cache mô tả liên kết giữa object bằng định danh logic. Khi nạp, JVM đọc tuần tự, materialize object vào heap hiện tại và giải quyết các định danh thành reference phù hợp với GC đang chạy.

Hai định dạng có trade-off khác nhau:

| Định dạng object | Cách nạp | Phụ thuộc GC | Đặc điểm |
|---|---|---|---|
| GC-specific / memory-mappable | Memory-map object theo bố cục tương thích | Có | Rất nhanh khi cache đã nóng trong filesystem page cache |
| GC-agnostic / streamable | Đọc tuần tự và materialize object theo heap hiện tại | Không | Dùng được với các GC khác nhau; cần thêm CPU cho công việc streaming/materialization |

Vì vậy, một cache streamable có thể được tạo trong môi trường G1 rồi nạp trong môi trường ZGC, miễn là ứng dụng, JDK release, OS và CPU architecture vẫn tương thích. Một cache memory-mappable không tự có khả năng này.

## 3. Đổi GC: trường hợp nào dùng lại được?

Giả sử cache được tạo trên Linux x86-64 bằng JDK 26 cho ứng dụng `orders-service`.

| Training | Production | Có thể dùng lại cache? | Điều kiện |
|---|---|---|---|
| G1 | G1 | Có | Cùng ứng dụng, JDK, OS/CPU; cả hai định dạng đều có thể phù hợp |
| G1 | ZGC | Có, nếu object archive là streamable | Định dạng GC-agnostic phải được tạo từ bước assembly |
| ZGC | G1 | Có, nếu object archive là streamable | Các chiều tương thích khác vẫn phải giữ nguyên |
| Parallel | Shenandoah | Có, nếu object archive là streamable | Cùng ứng dụng, JDK, OS/CPU |
| G1 | ZGC với cache memory-mappable phụ thuộc GC | Không được bảo đảm | Tạo lại cache bằng định dạng streamable |
| G1 trên Linux x86-64 | G1 trên Windows x86-64 | Không | OS khác; tạo cache cho Windows |
| G1 trên Linux x86-64 | G1 trên Linux AArch64 | Không | CPU architecture khác; tạo cache cho AArch64 |
| G1 trên JDK 26 | G1 trên JDK 27 | Không | JDK release khác; tạo cache bằng JDK 27 |

Bảng này tách đúng ý nghĩa của JEP 516: **GC có thể thay đổi khi cache dùng streamable format; ba chiều còn lại không được nới lỏng.**

Nếu production có nhiều cấu hình GC trên cùng một nền tảng, streamable cache giúp giảm nhu cầu tạo một bản cache riêng cho từng GC. Nếu production chạy trên nhiều OS hoặc CPU architecture, vẫn cần artifact riêng cho từng nền tảng.

## 4. Phụ thuộc vào ứng dụng: classpath, JAR và module path

AOT cache được tạo cho một ứng dụng cụ thể. JDK xác định ứng dụng qua cách khởi chạy, chẳng hạn:

- `-classpath`, `-cp` hoặc `-jar` đối với ứng dụng dùng class path.
- `--module-path` và module được khởi chạy đối với ứng dụng modular.

Các JAR và module tạo nên ứng dụng là một phần của danh tính cache. Nếu thay đổi binary hoặc dependency, cache cũ có thể không nạp được hoặc không còn đại diện cho ứng dụng mới.

Ví dụ:

| Thay đổi giữa training và production | Cách xử lý |
|---|---|
| Cùng JAR, cùng dependency và cùng cách khởi chạy | Có thể dùng cache nếu các chiều tương thích khác khớp |
| Thay `orders-service.jar` bằng bản build mới | Tạo lại cache |
| Nâng phiên bản một dependency JAR | Tạo lại cache |
| Thêm, bỏ hoặc đổi thứ tự entry trong classpath | Tạo lại cache và kiểm tra log |
| Thay module hoặc module path | Tạo lại cache |
| Đổi từ class path sang module path | Tạo lại cache |
| Giữ tên file JAR nhưng thay nội dung bên trong | Coi là ứng dụng mới; tạo lại cache |

Không chỉ tên file mới quan trọng. Một JAR có cùng tên nhưng nội dung đã thay đổi vẫn là binary khác. Vì vậy, pipeline nên gắn cache với fingerprint của artifact và dependency lockfile, thay vì chỉ dùng tên `app.aot` cố định.

Training workload cũng cần được phân biệt với application identity. Thay workload training không nhất thiết làm cache mất khả năng nạp nếu binary và các điều kiện tương thích vẫn giữ nguyên. Tuy nhiên, nếu workload mới đi qua nhiều đường code mà lần training trước chưa quan sát, cache có thể bỏ sót lớp hoặc object có ích. Khi hành vi production thay đổi đáng kể, hãy training lại để cải thiện độ bao phủ và lợi ích warmup.

## 5. Phụ thuộc vào JDK release

AOT cache được tạo cho một JDK release cụ thể. Cache tạo bằng JDK 26 không phải artifact dùng chung với JDK 27, kể cả khi:

- Ứng dụng dùng cùng source code.
- Các JAR và dependency không đổi.
- Cùng hệ điều hành và CPU.
- Cùng garbage collector.
- Object archive đã dùng định dạng GC-agnostic.

Ví dụ:

```text
Training:
  JDK 26 + orders-service.jar + Linux x86-64 + streamable cache

Production:
  JDK 27 + orders-service.jar + Linux x86-64 + ZGC

Kết quả:
  Không dùng lại cache JDK 26.
  Chạy training và assembly lại bằng JDK 27.
```

Khi nâng JDK, hãy tạo cache mới trong pipeline của release mới. Không chỉ đổi đường dẫn `JAVA_HOME` rồi giữ nguyên file cache cũ.

Đối với các bản cập nhật JDK trong cùng feature release, hãy quản lý JDK vendor/build/update như một phần của môi trường build đã kiểm soát. Tài liệu xác định cache theo JDK release; nếu nhà cung cấp JDK hoặc bản build có thay đổi về khả năng tương thích cache, làm theo release notes của bản đó. Trong pipeline cần độ tái lập cao, tạo lại cache sau khi đổi JDK build là cách an toàn và dễ kiểm chứng.

## 6. Phụ thuộc vào OS và CPU architecture

AOT cache còn gắn với hệ điều hành và kiến trúc CPU của môi trường tạo cache. Định dạng streamable chỉ trung lập với cách GC bố trí object/reference; nó không chuyển cache thành định dạng nhị phân đa nền tảng.

Ví dụ:

| Nền tảng training | Nền tảng production | Cách xử lý |
|---|---|---|
| Linux x86-64 | Linux x86-64 | Có thể dùng lại nếu các điều kiện khác khớp |
| Linux x86-64 | Windows x86-64 | Tạo cache riêng cho Windows |
| Linux x86-64 | macOS AArch64 | Tạo cache riêng cho macOS AArch64 |
| Linux AArch64 | Linux x86-64 | Tạo cache riêng cho x86-64 |
| Windows AArch64 | Windows x86-64 | Tạo cache riêng cho x86-64 |

Tài liệu JDK nêu ràng buộc ở mức OS và CPU architecture. Không nên suy diễn rằng phải cùng model CPU hoặc cùng một thế hệ vi kiến trúc nếu tài liệu không yêu cầu điều đó. Tuy nhiên, khi triển khai trên nhiều loại CPU, vẫn phải kiểm thử đúng nền tảng đích và xác nhận JVM nạp được cache.

Trong CI/CD, hãy tạo cache theo từng cặp nền tảng, ví dụ:

- `linux-x64`
- `linux-aarch64`
- `windows-x64`
- `macos-aarch64`

Tên này chỉ là quy ước artifact của pipeline, không phải tên chuẩn do JVM quy định.

## 7. JVM options và agent cũng có thể làm cache không tương thích

Ngay cả khi ứng dụng, JDK, OS và CPU đều đúng, cache vẫn có thể không nạp được nếu runtime dùng các tùy chọn JVM không tương thích.

Tài liệu JDK 26 nêu ví dụ về một số tùy chọn JVMTI. Các agent có khả năng can thiệp class loading hoặc biến đổi bytecode có thể khiến dữ liệu AOT đã ghi không còn phù hợp với các lớp thực tế lúc production.

Một số điểm cần giữ nhất quán:

- Cùng classpath/module path và binary ứng dụng.
- Cùng những tùy chọn ảnh hưởng đến class loading, linking hoặc module graph khi chúng là một phần của điều kiện cache.
- Kiểm tra các JVMTI agent, class-file load hook, profiler hoặc công cụ monitoring có biến đổi lớp.
- Nếu training bật `-XX:+AOTClassLinking`, cần kiểm tra các giới hạn tương thích của tùy chọn này ở production.
- Không tự ý thêm `--patch-module`, `--upgrade-module-path` hoặc các tùy chọn chẩn đoán làm thay đổi môi trường lớp mà không kiểm tra khả năng dùng cache.

Không có cam kết rằng AOT cache tương thích với mọi tổ hợp JVM options. Đây là artifact tối ưu hóa; một số cấu hình runtime có thể làm cache bị từ chối.

## 8. Cách kiểm tra cache có thực sự được nạp

JDK 26 hỗ trợ hai hành vi chính khi production dùng cache:

- `-XX:AOTMode=auto`: chế độ mặc định. Nếu cache không thể được dùng, JVM tiếp tục chạy mà không có AOT cache. Đây là lựa chọn được khuyến nghị cho production.
- `-XX:AOTMode=on`: chế độ fail-fast trong JDK 26. Nếu cache không thể được nạp, JVM báo lỗi và thoát. Dùng trong kiểm thử tương thích, không nên mặc định dùng cho production nếu cache có thể bị thay đổi ngoài kiểm soát.

Bật log AOT để xem lý do cache được dùng hoặc bị bỏ qua:

```bash
java -XX:AOTMode=auto \
     -XX:AOTCache=orders-linux-x64.aot \
     -Xlog:aot \
     -cp orders-service.jar com.example.Main
```

Trong pipeline kiểm thử, có thể dùng chế độ fail-fast:

```bash
java -XX:AOTMode=on \
     -XX:AOTCache=orders-linux-x64.aot \
     -Xlog:aot \
     -cp orders-service.jar com.example.Main
```

Nếu cache không được nạp, kiểm tra log và xác minh lần lượt:

1. File cache có tồn tại, đọc được và đúng artifact của ứng dụng không?
2. Ứng dụng, classpath, JAR hoặc module path có thay đổi không?
3. JDK release có giống lúc tạo cache không?
4. OS và CPU architecture có giống không?
5. Cache object có ở định dạng streamable nếu production dùng GC khác không?
6. JVM options, JVMTI agent hoặc công cụ instrumentation có thay đổi không?

Không coi việc ứng dụng khởi động thành công là bằng chứng cache đã được sử dụng. Với chế độ `auto`, JVM có thể bỏ qua cache rồi chạy bình thường. Phải xem `-Xlog:aot` hoặc dùng chế độ fail-fast trong test để xác nhận.

## 9. Ví dụ triển khai: một ứng dụng, hai GC, một nền tảng

Giả sử ứng dụng `orders-service.jar` được training bằng JDK 26 trên Linux x86-64. Production có hai nhóm máy: nhóm G1 và nhóm ZGC. Để dùng chung cache cho cả hai nhóm, tạo object archive theo định dạng streamable.

Giai đoạn training:

```bash
java -XX:AOTMode=record \
     -XX:AOTConfiguration=orders.aotconfig \
     -cp orders-service.jar \
     com.example.Main
```

Giai đoạn assembly với định dạng streamable:

```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+AOTStreamableObjects \
     -XX:AOTMode=create \
     -XX:AOTConfiguration=orders.aotconfig \
     -XX:AOTCache=orders-linux-x64.aot \
     -cp orders-service.jar
```

Production trên nhóm G1:

```bash
java -XX:+UseG1GC \
     -XX:AOTMode=auto \
     -XX:AOTCache=orders-linux-x64.aot \
     -cp orders-service.jar \
     com.example.Main
```

Production trên nhóm ZGC:

```bash
java -XX:+UseZGC \
     -XX:AOTMode=auto \
     -XX:AOTCache=orders-linux-x64.aot \
     -cp orders-service.jar \
     com.example.Main
```

Hai nhóm có thể dùng cùng cache vì object archive ở dạng GC-agnostic. Điều kiện là cả hai cùng ứng dụng, JDK release, Linux và x86-64. Nếu nhóm ZGC chạy JDK 27 hoặc AArch64, phải tạo cache riêng cho tổ hợp đó.

`-XX:+AOTStreamableObjects` là tùy chọn chẩn đoán để yêu cầu định dạng streamable khi tạo cache. Không cần bật lại tùy chọn này ở production chỉ để đọc cache đã được tạo ở định dạng đó. Hãy xác minh tùy chọn trên đúng bản JDK 26 đang dùng; đây không phải API Java ổn định và không cần thiết cho ứng dụng thông thường nếu heuristic đã tạo đúng định dạng.

## 10. Thiết kế cache matrix trong CI/CD

Một pipeline nhiều môi trường nên tạo cache như artifact có version, gắn với các đầu vào tạo ra nó. Một cache key khái niệm có thể gồm:

```text
application-id
+ application-artifact-fingerprint
+ dependency-fingerprint
+ jdk-release
+ os
+ cpu-architecture
+ object-cache-format
```

Đây là quy ước quản lý artifact của pipeline, không phải công thức hash nội bộ của HotSpot.

Ví dụ ma trận triển khai:

| Ứng dụng | JDK | OS | CPU architecture | Object format | Artifact |
|---|---|---|---|---|---|
| orders-service v42 | 26 | Linux | x86-64 | Streamable | `orders-v42-jdk26-linux-x64.aot` |
| orders-service v42 | 26 | Linux | AArch64 | Streamable | `orders-v42-jdk26-linux-arm64.aot` |
| orders-service v42 | 26 | Windows | x86-64 | Streamable | `orders-v42-jdk26-windows-x64.aot` |
| orders-service v42 | 27 | Linux | x86-64 | Streamable | `orders-v42-jdk27-linux-x64.aot` |

Các cache trên có thể dùng chung giữa G1 và ZGC trong từng hàng nếu object archive streamable. Không chia sẻ cache giữa các hàng chỉ vì chúng đều dùng cùng GC.

Quy trình nên làm:

1. Build ứng dụng và khóa dependency.
2. Xác định JDK release, OS và CPU architecture của từng target.
3. Chạy training bằng artifact đúng với target đó.
4. Tạo cache và chọn object format phù hợp với chiến lược GC.
5. Kiểm tra cache trên đúng môi trường production-like bằng `-Xlog:aot`.
6. Lưu cache cùng metadata build và fingerprint ứng dụng.
7. Khi đổi app binary/dependency, JDK release, OS hoặc CPU architecture, tạo cache mới.
8. Khi chỉ đổi GC, xác nhận cache là streamable trước khi dùng lại.
9. Giữ chế độ `auto` ở production nếu cần JVM tiếp tục chạy khi cache không tương thích.

Không nên dùng một cache dùng chung giữa các service chỉ vì chúng cùng chạy trên một JDK và cùng CPU. Danh tính ứng dụng là một phần bắt buộc của cache.

## 11. Những thay đổi nào cần tạo lại cache?

| Thay đổi | Có cần tạo lại? | Lý do |
|---|---|---|
| G1 đổi sang ZGC, cache streamable | Không nhất thiết | Object archive không phụ thuộc GC |
| ZGC đổi sang G1, cache streamable | Không nhất thiết | Cùng điều kiện tương thích khác |
| G1 đổi sang ZGC, cache memory-mappable GC-specific | Có | Định dạng object phụ thuộc GC |
| Nâng JDK 26 lên JDK 27 | Có | JDK release là thành phần của cache identity |
| Thay JAR ứng dụng hoặc dependency | Có | Ứng dụng đã thay đổi |
| Đổi classpath hoặc module path | Có | Cách xác định ứng dụng đã thay đổi |
| Chuyển Linux sang Windows | Có | OS khác |
| Chuyển x86-64 sang AArch64 | Có | CPU architecture khác |
| Thay đổi workload training nhưng không đổi ứng dụng | Không bắt buộc về tương thích; nên training lại nếu muốn tăng độ bao phủ | Cache có thể vẫn nạp nhưng ít hữu ích hơn với workload mới |
| Thêm JVMTI agent hoặc tùy chọn làm thay đổi class loading | Phải kiểm tra; có thể cần tạo lại hoặc bỏ tùy chọn không tương thích | Runtime có thể không còn khớp điều kiện cache |
| Đổi vị trí file cache nhưng nội dung giữ nguyên | Không | Chỉ thay đường dẫn artifact, nếu JVM vẫn đọc được |

Bảng này giúp phân biệt hai việc: **cache không tương thích** và **cache tương thích nhưng không còn tối ưu**. Thay đổi ứng dụng/JDK/OS/CPU thuộc nhóm phải tạo lại. Thay đổi workload training có thể chỉ làm giảm lợi ích, nhưng vẫn nên ghi lại để cache phản ánh startup path mới.

## 12. Các lỗi hiểu nhầm cần tránh

- **“JEP 516 làm cache dùng được trên mọi OS và CPU.”** Sai. Nó làm định dạng object độc lập với GC; OS và CPU architecture vẫn là điều kiện tương thích.
- **“Cache streamable của JDK 26 dùng được trên JDK 27.”** Sai. JDK release vẫn là một phần của cache identity.
- **“Cùng GC thì có thể dùng chung cache cho nhiều ứng dụng.”** Sai. Cache được tạo cho một ứng dụng cụ thể.
- **“Chỉ cần cùng tên JAR là đủ.”** Sai. Binary và dependency thực tế phải tương thích; cùng tên file không bảo đảm cùng nội dung.
- **“Mọi cache tạo bằng JDK 26 đều GC-agnostic.”** Sai. JDK có thể tạo object archive memory-mappable hoặc streamable. Chỉ định dạng streamable loại bỏ phụ thuộc GC.
- **“Training trên G1 rồi production trên ZGC luôn dùng được.”** Chỉ đúng khi object archive là streamable và ứng dụng/JDK/OS/CPU cùng tương thích.
- **“Ứng dụng khởi động được nghĩa là AOT cache đã được dùng.”** Sai. Chế độ `auto` có thể bỏ qua cache rồi tiếp tục chạy.
- **“Cache có thể thay thế việc benchmark.”** Sai. AOT cache là tối ưu startup/warmup; phải đo trên workload và nền tảng đích.

## 13. Checklist phát hành

- [ ] Đã xác định fingerprint ứng dụng, JAR và dependency.
- [ ] Đã khóa JDK release dùng để training, assembly và production.
- [ ] Đã tạo artifact riêng cho từng OS và CPU architecture.
- [ ] Đã xác định GC production và object cache format.
- [ ] Nếu production có nhiều GC, đã xác nhận object archive là streamable.
- [ ] Đã kiểm tra các JVM options và JVMTI agent có thể ảnh hưởng cache.
- [ ] Đã chạy thử với `-Xlog:aot` và xác nhận cache thực sự được nạp.
- [ ] Đã kiểm thử fallback khi cache không tương thích.
- [ ] Đã tạo lại cache khi đổi ứng dụng, JDK release, OS hoặc CPU architecture.
- [ ] Đã training lại khi startup workload thay đổi đáng kể.
- [ ] Đã benchmark cold start, warm start, time-to-first-request và CPU materialization trên nền tảng đích.

## Tài liệu tham chiếu

1. [JEP 516 – Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516)
2. [Oracle Java SE 26 – The java Command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
3. [Oracle – Consolidated JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26all-relnotes.html)
4. [Inside.java – Performance Improvements in JDK 26](https://inside.java/2026/06/09/jdk-26-performance-improvements/)
5. [Inside.java – JDK 26 GC Changes](https://inside.java/2026/02/28/jdk26-gc-changes/)
6. [JEP 483 – Ahead-of-Time Class Loading and Linking](https://openjdk.org/jeps/483)

