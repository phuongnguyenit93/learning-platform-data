# Kiểm tra bản phân phối, nền tảng và cấu hình hỗ trợ Shenandoah

## 1. Mục tiêu: xác nhận đúng JDK trước khi bật Generational Shenandoah

Generational Shenandoah là chế độ thu gom rác theo thế hệ của Shenandoah GC, được hoàn thiện thành tính năng chính thức trong **JDK 25** qua **JEP 521**. Chế độ này giữ cách tiếp cận concurrent, low-pause của Shenandoah và bổ sung hai vùng thế hệ: young generation cho phần lớn object mới tạo, old generation cho object sống lâu hơn.

Tuy nhiên, **không phải mọi bản phân phối JDK 25 đều đóng gói Shenandoah**. Java SE không bắt buộc mọi implementation phải cung cấp cùng một garbage collector. Shenandoah là tính năng của HotSpot JVM; khả năng sử dụng phụ thuộc vào JDK vendor, build configuration, hệ điều hành và kiến trúc CPU của binary đang chạy.

Bài thuộc chương **Generational Shenandoah** của module **JAVA_VERSION_JAVA25**, với đề bài trực tiếp **“Kiểm tra bản phân phối, nền tảng và cấu hình hỗ trợ Shenandoah”**. Trọng tâm là xác minh binary thật sự có Shenandoah, kiểm tra môi trường được vendor hỗ trợ và chọn đúng flags của JDK 25. Nội dung chỉ dùng cơ chế còn áp dụng hiện nay; không lấy quy trình experimental của JDK 24 làm hướng dẫn triển khai cho JDK 25.

### Sau bài này, bạn có thể

1. Giải thích Generational Shenandoah và trạng thái chính thức của JEP 521.
2. Phân biệt Java version, JDK distribution, JVM implementation và GC được build vào binary.
3. Đánh giá khả năng hỗ trợ theo vendor, OS và CPU architecture.
4. Nhận biết vì sao cùng Java 25 nhưng hai binary có thể có danh sách GC khác nhau.
5. Kiểm tra Shenandoah bằng lệnh khởi chạy, flags và GC logs.
6. Bật generational mode đúng cú pháp, không dùng cờ experimental đã lỗi thời cho Java 25.
7. Đánh giá giới hạn, hiệu năng, tài nguyên và điều kiện triển khai trong container/production.

## 2. Generational Shenandoah là gì?

Shenandoah là garbage collector của HotSpot, thực hiện phần lớn công việc đánh dấu và di chuyển object đồng thời với ứng dụng. Mục tiêu của nó là giữ các khoảng dừng GC ngắn, không tăng tuyến tính trực tiếp theo dung lượng heap như các cách thu gom toàn heap truyền thống.

**Generational Shenandoah** bổ sung mô hình hai thế hệ:

- **Young generation:** nơi object mới được cấp phát; phần lớn object ứng dụng thường trở thành unreachable khá sớm.
- **Old generation:** nơi object sống qua nhiều chu kỳ collection và tiếp tục được ứng dụng tham chiếu.

~~~mermaid
flowchart TD
    A["Object mới được cấp phát"] --> B["Young generation"]
    B --> C{"Object còn sống qua collection?"}
    C -->|Không| D["Thu hồi vùng nhớ"]
    C -->|Có| E["Promotion"]
    E --> F["Old generation"]
    F --> G["Old-generation collection theo nhu cầu"]
    G --> H["Thu hồi object không còn reachable"]
~~~

Mô hình này tận dụng *weak generational hypothesis*: phần lớn object mới tạo có vòng đời ngắn. GC có thể tập trung thu gom young generation thường xuyên, trong khi old generation được xử lý ít thường xuyên hơn. Nhờ vậy, một số workload có allocation rate cao có thể giảm lượng công việc GC không cần thiết.

Generational mode vẫn dựa trên thiết kế concurrent của Shenandoah. Nó không có nghĩa mọi pha GC đều chạy hoàn toàn không dừng ứng dụng; một số pha ngắn vẫn cần phối hợp với application threads. Không coi Shenandoah là hard real-time collector hoặc cam kết pause time bằng không.

## 3. Trạng thái JEP 521 trong Java 25

| JDK | Trạng thái generational mode | Cách sử dụng |
| --- | --- | --- |
| JDK 24 | Experimental theo JEP 404 | Cần mở khóa experimental VM options |
| **JDK 25** | **Product feature theo JEP 521** | **Dùng trực tiếp flags của Shenandoah; không cần unlock experimental** |

JEP 521 đưa generational mode ra khỏi trạng thái experimental trong JDK 25. Người vận hành có thể bật bằng:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -jar app.jar
~~~

Trong Java 25, không cần thêm `-XX:+UnlockExperimentalVMOptions` chỉ để bật generational mode. Đây là khác biệt quan trọng so với giai đoạn thử nghiệm ở JDK 24.

**Generational mode vẫn là lựa chọn phải bật tường minh trong JDK 25.** Mặc định của Shenandoah vẫn là mode `satb` đơn thế hệ. Vì vậy, chỉ thêm `-XX:+UseShenandoahGC` sẽ chọn Shenandoah, nhưng chưa đồng nghĩa đang chạy generational mode.

Nguồn chuẩn: [JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521) và [JEP 404 — Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404).

## 4. Tách bốn lớp thông tin khi kiểm tra hỗ trợ

Khi nói “JDK 25 hỗ trợ Shenandoah”, cần xác định đang nói về bốn lớp khác nhau:

| Lớp | Câu hỏi | Ví dụ kiểm tra |
| --- | --- | --- |
| Java/JDK release | Binary có đúng Java 25 không? | `java -version` |
| Distribution/vendor | Ai build và đóng gói binary? | `java.vendor`, package metadata |
| JVM implementation | Đang chạy HotSpot hay VM khác? | `java.vm.name` |
| GC availability | Shenandoah có được compile/package vào binary này không? | Khởi chạy với flags Shenandoah và đọc GC log |

Java SE specification không yêu cầu mọi JDK vendor phải cung cấp Shenandoah. Một JDK có thể tuân thủ Java 25 nhưng chỉ đóng gói một tập garbage collector nhất định.

Shenandoah là collector thuộc **HotSpot**. Nếu runtime sử dụng JVM implementation khác, không thể mặc định các HotSpot flags sẽ tồn tại hoặc có cùng ngữ nghĩa.

**Quy tắc vận hành:** kiểm tra chính binary mà ứng dụng sẽ dùng. Tên thư mục cài đặt, tên image container, version string hoặc việc một JDK khác trên cùng máy có Shenandoah đều không chứng minh binary hiện tại hỗ trợ collector này.

## 5. Khả năng theo bản phân phối JDK 25

Các ví dụ dưới đây giúp định hướng chọn binary. Danh sách không thay thế tài liệu hỗ trợ chính thức của vendor cho từng bản update, OS và kiến trúc.

| Bản phân phối | Tình trạng Shenandoah trong JDK 25 | Cách xác nhận |
| --- | --- | --- |
| Red Hat build of OpenJDK 25 | Red Hat xác nhận có Shenandoah; generational mode được bật bằng `-XX:ShenandoahGCMode=generational` | Kiểm tra đúng package và nền tảng được Red Hat hỗ trợ |
| Azul Zulu 25 | Release notes có các bản sửa lỗi riêng cho Shenandoah, cho thấy collector có trong build tương ứng | Kiểm tra package Zulu cụ thể và chạy probe |
| Oracle JDK 25 | Tài liệu GC của Oracle cho JDK 25 liệt kê Serial, Parallel, G1 và ZGC; không liệt kê Shenandoah | Không giả định binary Oracle JDK 25 có Shenandoah; kiểm tra trực tiếp trước khi cấu hình |
| Các bản phân phối khác | Không suy ra chỉ từ tên OpenJDK hoặc Java 25 | Đối chiếu release notes/vendor support và chạy probe trên binary thật |

### Red Hat build of OpenJDK 25

Tài liệu Red Hat xác nhận Red Hat build of OpenJDK bao gồm Shenandoah. Đối với JDK 25, tài liệu distribution selection nêu các nền tảng RHEL 9 và RHEL 10; Red Hat không cung cấp bản Red Hat build of OpenJDK 25 cho Windows. Red Hat phân phối Eclipse Temurin 25 cho Windows, đây là binary khác và cần xác minh theo tài liệu Temurin.

Điều này cho thấy phải tách **có collector trong build** khỏi **vendor có cung cấp binary trên nền tảng đang dùng**.

### Azul Zulu 25

Release notes của Azul Zulu 25 GA có các bản sửa lỗi mang nhãn Shenandoah. Đây là bằng chứng cho thấy dòng build này có implementation Shenandoah. Tuy vậy, vẫn cần đối chiếu package và kiến trúc cụ thể đang tải; danh sách nền tảng download không tự động bảo đảm mọi package có cùng cấu hình GC.

### Oracle JDK 25

Tài liệu Oracle JDK 25 về các collector khả dụng mô tả Serial, Parallel, G1 và ZGC. Tài liệu `java` của JDK 25 cũng không liệt kê các flags Shenandoah. Vì vậy, khi dùng Oracle JDK 25, không đưa flags Shenandoah vào production config với giả định chúng sẽ hoạt động. Nếu nhu cầu bắt buộc dùng Shenandoah, chọn một bản phân phối có xác nhận hỗ trợ và kiểm thử binary đó.

Tài liệu tham khảo:

- [Red Hat build of OpenJDK 25 — Overview](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/getting_started_with_red_hat_build_of_openjdk_25/openjdk-overview)
- [Red Hat build of OpenJDK 25 — Distribution selection](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/getting_started_with_red_hat_build_of_openjdk_25/openjdk-distribution-selection)
- [Azul Zulu 25 GA Release Notes](https://docs.azul.com/core/pdfs/25-ga/azul-zulu-ca-release-notes-25-ga-rev1.0.pdf)
- [Oracle JDK 25 — Available Collectors](https://docs.oracle.com/en/java/javase/25/gctuning/available-collectors.html)

## 6. Kiểm tra OS và CPU architecture

Việc Shenandoah tồn tại trong mã nguồn OpenJDK không có nghĩa mọi vendor đều build và phân phối nó cho mọi OS/CPU. Hãy kiểm tra hai lớp riêng:

1. **Upstream port/build support:** mã nguồn và port của Shenandoah có thể chạy trên nền tảng nào.
2. **Vendor distribution support:** vendor có phát hành, kiểm thử và hỗ trợ binary cho đúng OS/CPU đó không.

Tổng quan upstream Shenandoah mô tả Linux là nền tảng chính được kiểm thử liên tục; Windows là mục tiêu phụ; macOS được cộng đồng kiểm thử. Với CPU, x86_64 và AArch64 là các mục tiêu chính; một số kiến trúc khác ở mức community-tested hoặc chưa hỗ trợ. Đây là trạng thái port upstream, không phải cam kết hỗ trợ sản phẩm của từng vendor. Trang hỗ trợ upstream còn có các dòng lịch sử cho nhiều JDK/kiến trúc; chỉ dùng phần OS/CPU như bối cảnh porting, không coi đó là ma trận binary JDK 25 đã được vendor chứng nhận.

| Nền tảng | Trạng thái upstream được công bố | Điều cần xác nhận ở vendor |
| --- | --- | --- |
| Linux | Mục tiêu chính, kiểm thử liên tục | Distro, kernel, libc, kiến trúc và package JDK |
| Windows | Mục tiêu phụ, kiểm thử liên tục | Windows version, CPU architecture và build variant |
| macOS | Kiểm thử bởi cộng đồng | Phiên bản macOS, x64/Apple Silicon và package |
| x86_64 | Mục tiêu CPU chính | Binary đúng kiến trúc 64-bit |
| AArch64 | Mục tiêu CPU chính | Binary ARM64 và OS vendor hỗ trợ |
| PPC64 / RISC-V64 | Mức community-tested trong upstream overview | Chỉ dùng khi vendor xác nhận build và support |
| S390X / SPARC | Upstream overview không liệt kê là mục tiêu hỗ trợ | Không giả định có Shenandoah |

JDK 25 đã loại bỏ port 32-bit x86 theo JEP 503. Không dùng bảng port cũ có x86_32 để kết luận binary Java 25 còn hỗ trợ nền tảng đó.

### Không dùng bảng certified platform để suy ra GC

Ví dụ, Oracle JDK 25 có danh sách OS/CPU được chứng nhận. Danh sách này chỉ cho biết nền tảng cài và chạy Oracle JDK được chứng nhận; nó không chứng minh Oracle JDK 25 có mọi GC của upstream OpenJDK. Phải xem riêng danh sách collector của vendor và xác nhận runtime.

Nguồn upstream: [OpenJDK Shenandoah GC — Support Overview](https://wiki.openjdk.org/display/shenandoah/Support).

## 7. Xác định binary thực sự đang chạy

Trước khi thêm flags, ghi lại thông tin runtime từ chính môi trường triển khai.

~~~bash
java -version
~~~

Lệnh này hiển thị version, vendor/runtime và VM build. Tiếp theo, xem các thuộc tính môi trường:

~~~bash
java -XshowSettings:properties -version
~~~

Tập trung vào các thuộc tính:

| Property | Ý nghĩa |
| --- | --- |
| `java.version` | Phiên bản Java |
| `java.vendor` | Nhà cung cấp JDK |
| `java.vm.name` | Tên JVM implementation |
| `java.vm.vendor` | Nhà cung cấp JVM |
| `java.vm.version` | Phiên bản/build VM |
| `os.name` | Hệ điều hành |
| `os.arch` | Kiến trúc CPU |

Nếu máy có nhiều JDK, xác định đường dẫn thực của executable:

Linux/macOS:

~~~bash
which java
readlink -f "$(which java)"
~~~

Windows PowerShell:

~~~powershell
Get-Command java | Select-Object -ExpandProperty Source
~~~

Đừng chỉ dựa vào `JAVA_HOME` nếu process service, container entrypoint hoặc process manager đang gọi một binary khác qua PATH.

## 8. Probe xem binary có Shenandoah hay không

Cách trực tiếp nhất là yêu cầu JVM chọn Shenandoah và in GC log lúc khởi động:

~~~bash
java -XX:+UseShenandoahGC -Xlog:gc -version
~~~

Nếu binary có Shenandoah, log GC sẽ cho biết collector được chọn. Nếu JVM báo không nhận diện option hoặc collector không được hỗ trợ, binary đó không cung cấp Shenandoah trong cấu hình hiện tại.

Sau khi xác nhận collector tồn tại, thử generational mode:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xlog:gc -version
~~~

Lệnh này kiểm tra đồng thời hai điều kiện: Shenandoah có trong binary và mode generational được chấp nhận.

### Kiểm tra giá trị flags

Có thể in các VM flags sau khi khởi động:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -XX:+PrintFlagsFinal -version
~~~

Tìm các flag:

- `UseShenandoahGC`
- `ShenandoahGCMode`
- `ShenandoahGCHeuristics`

Với mode generational, giá trị mode cần là `generational`. Heuristics mặc định là `adaptive`.

**Probe bằng `-version` chỉ xác nhận VM chấp nhận cấu hình lúc khởi động.** Nó chưa chứng minh workload thực tế chạy ổn định hoặc có lợi về latency/throughput. Sau probe, hãy chạy smoke test và workload đại diện có bật GC logging.

## 9. Bật Generational Shenandoah đúng cách trên Java 25

Cấu hình tối thiểu:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -jar app.jar
~~~

Ý nghĩa:

| Flag | Tác dụng |
| --- | --- |
| `-XX:+UseShenandoahGC` | Chọn Shenandoah GC |
| `-XX:ShenandoahGCMode=generational` | Chọn chế độ young/old generation |
| `-jar app.jar` | Khởi chạy ứng dụng |

Nếu ứng dụng cần ghi log để quan sát trong giai đoạn thử nghiệm:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc \
  -jar app.jar
~~~

Không đồng thời bật một collector khác như `-XX:+UseG1GC` hoặc `-XX:+UseZGC`. Mỗi JVM chỉ chọn một GC cho heap.

### Mặc định vẫn là mode đơn thế hệ

Trong Java 25, `ShenandoahGCMode` mặc định là `satb`, tức chế độ single-generation. Nếu muốn dùng generational, phải cấu hình tường minh `-XX:ShenandoahGCMode=generational`.

Chỉ thêm `-XX:+UseShenandoahGC` mà quên mode này sẽ chạy Shenandoah đơn thế hệ, không phải bài thực hành Generational Shenandoah.

## 10. Heuristics: giữ cấu hình được hỗ trợ

`ShenandoahGCHeuristics` quyết định khi nào GC bắt đầu chu kỳ và điều chỉnh cách xử lý trong chu kỳ. Heuristics mặc định là `adaptive`.

Với generational mode trong JDK 25, `adaptive` là lựa chọn được hỗ trợ. Không sao chép các cấu hình `static` hoặc `compact` từ ví dụ single-generation rồi áp dụng cho generational mode.

| Heuristics | Ý nghĩa tổng quát | Với generational mode JDK 25 |
| --- | --- | --- |
| `adaptive` | Điều chỉnh chu kỳ theo tình trạng heap và lượng free space mục tiêu | Được hỗ trợ; là mặc định |
| `static` | Kích hoạt GC dựa trên ngưỡng free heap | Không phải lựa chọn được hỗ trợ cho generational |
| `compact` | Chạy chu kỳ thường xuyên hơn để thu hồi thêm vùng nhớ | Không phải lựa chọn được hỗ trợ cho generational |

Thông thường, bắt đầu với mặc định:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -jar app.jar
~~~

Không cần thêm `-XX:ShenandoahGCHeuristics=adaptive` nếu không có lý do ghi rõ cấu hình; JVM đã dùng giá trị mặc định này.

Nguồn đối chiếu: [Java launcher options — Shenandoah flags](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html). Tài liệu JDK 26 giữ cùng ngữ nghĩa flags; khi chạy JDK 25, luôn kiểm tra binary và tài liệu update tương ứng.

## 11. Vì sao không dùng UnlockExperimentalVMOptions trong Java 25?

Trong JDK 24, generational Shenandoah được giới thiệu dưới dạng experimental theo JEP 404. Khi đó, người dùng phải thêm `-XX:+UnlockExperimentalVMOptions` để mở khóa mode.

Từ JDK 25, JEP 521 đưa generational mode thành product feature. Cấu hình hiện hành chỉ cần:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -jar app.jar
~~~

Không cần mang cờ unlock experimental từ script JDK 24 sang Java 25. Việc giữ cờ cũ không làm cấu hình đúng hơn và có thể gây hiểu nhầm rằng generational mode vẫn là experimental.

Khi nâng từ JDK 24:

1. Kiểm tra binary JDK 25 có Shenandoah.
2. Bỏ phụ thuộc vào cờ unlock experimental chỉ phục vụ JEP 404.
3. Giữ hai flags chọn Shenandoah và generational mode.
4. Chạy lại GC logs, smoke tests và performance tests trên đúng build mới.

## 12. Kiểm tra cấu hình trong container

Một lỗi phổ biến là host có JDK hỗ trợ Shenandoah nhưng container lại chứa một JRE/JDK khác không có collector.

Hãy chạy probe **bên trong image**:

~~~bash
docker run --rm --entrypoint java my-app:tag \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc \
  -version
~~~

Nếu ứng dụng chạy qua Kubernetes, kiểm tra command/args và image digest của Pod đang thực thi; đừng suy ra từ image tag ở máy developer.

Checklist container:

- Image dùng đúng vendor/build có Shenandoah.
- Binary trong image là Java 25 update được hỗ trợ.
- OS base image và CPU architecture phù hợp với package.
- Không dùng multi-stage build khiến runtime image lấy nhầm JRE từ stage khác.
- GC flags nằm trong command/entrypoint thực sự được chạy.
- Memory limit của container đủ cho heap và phần native memory.
- Logs có thể được thu thập sau khi rollout.

Trong Linux container, HotSpot có khả năng nhận biết giới hạn tài nguyên container. Tuy vậy, heap size phải được kiểm tra theo memory limit thực tế; không đặt `-Xmx` vượt ngân sách bộ nhớ của Pod.

## 13. Chọn heap và giữ đủ khoảng trống cho concurrent GC

Shenandoah thực hiện phần lớn công việc GC đồng thời với ứng dụng. Trong lúc GC đang chạy, ứng dụng vẫn tiếp tục cấp phát object. Do đó, heap cần đủ khoảng trống để hấp thụ allocation trong thời gian collector hoàn tất chu kỳ.

Ví dụ cấu hình giới hạn heap:

~~~bash
java \
  -Xms1g \
  -Xmx4g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc \
  -jar app.jar
~~~

Các giá trị heap trên chỉ là ví dụ, không phải cấu hình khuyến nghị chung. Chọn `-Xms` và `-Xmx` theo:

- Live data set thực tế.
- Allocation rate ở tải bình thường và tải đỉnh.
- Container memory limit hoặc RAM máy.
- Số lượng concurrent GC threads và CPU có thể cấp cho JVM.
- Mức headroom cần thiết cho GC, metaspace, thread stacks, direct buffers và native libraries.

Nếu allocation pressure vượt khả năng thu gom, Shenandoah có thể phải pacing các allocating threads, chuyển sang degenerated GC hoặc full GC. Những sự kiện này có thể làm latency tăng dù collector hướng tới low pause.

## 14. Xác nhận generational mode bằng GC logs

Bật unified logging:

~~~bash
java \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc*,gc+ergo=debug:file=gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

Trong workload có cấp phát đủ lớn, log có thể thể hiện trigger hoặc chu kỳ GC thuộc young generation. Dựa vào log thực tế để xác nhận mode, không chỉ nhìn một dòng ứng dụng khởi động thành công.

### Các dấu hiệu cần theo dõi

| Dấu hiệu | Ý nghĩa điều tra |
| --- | --- |
| Young GC thường xuyên | Có thể là hoạt động bình thường của generational mode |
| Old-generation collection | Xử lý vùng object sống lâu |
| Pacing | Application threads bị điều tiết allocation khi GC cần thêm thời gian |
| Degenerated GC | Một chu kỳ concurrent không theo kịp và cần tiếp tục công việc trong pause |
| Full GC | Tình trạng nghiêm trọng hơn; cần kiểm tra heap headroom, live set và allocation |
| Concurrent cycle kéo dài | Có thể do live data lớn, thiếu CPU hoặc allocation pressure cao |

Không đánh giá GC chỉ từ tổng số chu kỳ. Đối chiếu pause time, concurrent time, allocation rate, throughput và request latency dưới cùng workload.

## 15. Xác minh flags trên process đang chạy

Nếu service đã chạy, có thể dùng `jcmd` để kiểm tra flags và command line của JVM:

~~~bash
jcmd -l
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
~~~

Thay `<pid>` bằng process ID thực tế. Kiểm tra:

- Process có dùng đúng JDK binary không.
- `UseShenandoahGC` có được bật không.
- `ShenandoahGCMode` có phải `generational` không.
- Có flag GC khác xung đột trong command line không.
- Heap size và các option liên quan có khớp deployment manifest không.

Nếu `jcmd` attach không hoạt động trong container, kiểm tra user chạy process, quyền attach và cấu hình container. Không kết luận GC chưa bật chỉ vì công cụ attach bị giới hạn; hãy đối chiếu startup command và GC log.

## 16. Những giới hạn cần hiểu trước khi triển khai

Generational Shenandoah là product feature trong JDK 25, nhưng kết quả vẫn phụ thuộc workload và môi trường.

### Giới hạn về phân phối

- Một số vendor không đóng gói Shenandoah.
- Một số vendor chỉ hỗ trợ JDK 25 trên tập OS/CPU nhất định.
- Một binary có Shenandoah chưa chắc hỗ trợ mọi nền tảng mà upstream code có thể port.
- Container image có thể dùng runtime khác với host.

### Giới hạn về hiệu năng

- Concurrent GC sử dụng CPU song song với ứng dụng.
- Barriers và việc di chuyển object có thể tạo overhead.
- Heap thiếu headroom làm tăng nguy cơ pacing hoặc degenerated/full GC.
- Pause time vẫn phụ thuộc root set và các pha cần phối hợp với application threads.
- Không có bảo đảm workload nào cũng nhanh hơn G1 hoặc ZGC.

### Giới hạn về cấu hình

- Generational mode cần được bật tường minh trong JDK 25.
- Heuristics được hỗ trợ cho generational mode là `adaptive`.
- Không áp dụng flags experimental của JDK 24 như hướng dẫn mặc định cho Java 25.

## 17. So sánh với G1 và ZGC trước khi chọn

Shenandoah không phải collector mặc định và không phải lựa chọn tối ưu cho mọi ứng dụng. Hãy so sánh trên workload thực tế.

| Tiêu chí | G1 | ZGC | Generational Shenandoah |
| --- | --- | --- | --- |
| Mục tiêu chính | Cân bằng throughput và pause-time goals | Latency rất thấp, heap lớn | Low-pause concurrent GC với generational collection |
| Chọn mặc định | Thường là default trên server-class HotSpot | Phải chọn tường minh | Phải chọn tường minh |
| Generational | Có | Generational mode là mặc định ở các JDK hiện đại | Bật tường minh bằng mode flag |
| Nền tảng | Rộng trong các HotSpot distributions | Tùy build và JDK | Tùy build và JDK |
| Cách quyết định | Baseline phù hợp cho nhiều ứng dụng | Cân nhắc khi latency rất quan trọng | Cân nhắc khi cần low pauses và binary hỗ trợ Shenandoah |

Đừng chọn Shenandoah chỉ vì pause time được quảng bá thấp. Hãy đo:

- p95/p99 pause time.
- End-to-end request latency.
- Throughput dưới tải ổn định và tải đột biến.
- CPU utilization và GC CPU time.
- RSS/heap occupancy.
- Số lần pacing, degenerated GC và full GC.

Nếu G1 đã đáp ứng SLO với chi phí vận hành thấp, không cần đổi collector chỉ để dùng một tính năng mới.

## 18. Quy trình kiểm tra trước khi rollout

Có thể áp dụng checklist theo thứ tự sau:

~~~mermaid
flowchart TD
    A["Xác định JDK vendor, build và VM"] --> B{"Binary có Shenandoah?"}
    B -->|Không| C["Chọn bản phân phối có hỗ trợ hoặc giữ GC hiện tại"]
    B -->|Có| D["Kiểm tra OS và CPU architecture"]
    D --> E{"Vendor hỗ trợ nền tảng này?"}
    E -->|Không| C
    E -->|Có| F["Chạy probe generational mode"]
    F --> G{"Flags được chấp nhận?"}
    G -->|Không| C
    G -->|Có| H["Chạy smoke test và thu GC logs"]
    H --> I["Benchmark workload đại diện"]
    I --> J{"Đạt SLO và ngân sách tài nguyên?"}
    J -->|Không| K["Điều chỉnh heap/workload hoặc chọn GC khác"]
    J -->|Có| L["Canary rồi rollout"]
~~~

### Các bước thực tế

1. Ghi nhận vendor, version, build, VM name, OS và CPU architecture.
2. Đối chiếu release notes và supported platforms của vendor.
3. Chạy probe `-XX:+UseShenandoahGC`.
4. Chạy probe thêm `-XX:ShenandoahGCMode=generational`.
5. Kiểm tra log và flags để xác nhận mode.
6. Chạy smoke/integration test.
7. Benchmark với G1 hoặc collector hiện tại làm baseline.
8. Triển khai canary và theo dõi GC logs, latency, throughput, CPU và RSS.
9. Chỉ rollout rộng khi có bằng chứng đáp ứng SLO và khả năng rollback rõ ràng.

## 19. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Unrecognized VM option 'UseShenandoahGC'` | Binary không build Shenandoah hoặc VM không hỗ trợ flag | Xác định vendor/build; chọn binary có Shenandoah |
| `ShenandoahGCMode` không được nhận diện | Runtime không có Shenandoah hoặc version/build không hỗ trợ mode | Chạy `java -version` và probe trên đúng binary |
| Chỉ thấy Shenandoah nhưng không có young collections | Chỉ bật `UseShenandoahGC`, chưa bật generational mode hoặc workload chưa kích hoạt collection | Kiểm tra `ShenandoahGCMode` và tạo workload allocation đại diện |
| Container chạy được trên host nhưng không chạy trong image | JDK trong image khác host | Chạy probe từ bên trong container |
| Startup báo lỗi do nhiều GC flags | Có cấu hình collector xung đột | Chỉ giữ một GC selection flag |
| Heuristics không hợp lệ ở generational mode | Đang đặt `static` hoặc `compact` | Bỏ override và dùng `adaptive` |
| Pacing xuất hiện thường xuyên | GC không theo kịp allocation hoặc thiếu heap/CPU headroom | Phân tích allocation, live set, heap và CPU quota |
| Degenerated/full GC tăng | Concurrent cycles không thu hồi đủ nhanh | Kiểm tra GC logs, heap headroom, live data và allocation bursts |
| Pause thấp nhưng throughput giảm | Concurrent work/barriers tiêu thụ thêm CPU | Đo CPU, throughput và request latency; so sánh G1/ZGC |
| Flag cũ yêu cầu experimental unlock | Đang dùng script JDK 24 | Chuyển sang cấu hình product feature của JDK 25 |

## 20. Bài thực hành: xác minh bản phân phối và bật generational mode

### Bối cảnh

Bạn nhận một ứng dụng Spring Boot chạy trong container Java 25. Nhóm muốn thử Generational Shenandoah để giảm pause time khi ứng dụng có allocation rate cao.

### Nhiệm vụ

1. Ghi lại output `java -version`.
2. Xem `java.vendor`, `java.vm.name`, `java.vm.version`, `os.name` và `os.arch` bằng `-XshowSettings:properties`.
3. Xác định binary thuộc Oracle JDK, Red Hat build, Azul Zulu hay distribution khác.
4. Đối chiếu vendor documentation để xác nhận Shenandoah được đóng gói trên OS/CPU đó.
5. Chạy probe:

~~~bash
java -XX:+UseShenandoahGC -Xlog:gc -version
~~~

6. Chạy probe generational:

~~~bash
java -XX:+UseShenandoahGC -XX:ShenandoahGCMode=generational -Xlog:gc -version
~~~

7. Chạy ứng dụng thử với:

~~~bash
java \
  -Xms1g \
  -Xmx4g \
  -XX:+UseShenandoahGC \
  -XX:ShenandoahGCMode=generational \
  -Xlog:gc*,gc+ergo=debug:file=gc.log:time,uptime,level,tags \
  -jar app.jar
~~~

8. Tạo workload đại diện với request mix và allocation rate gần production.
9. Kiểm tra young/old GC activity, pause time, throughput, CPU, RSS, pacing và degenerated/full GC.
10. Chạy cùng workload với collector hiện tại để so sánh.
11. Viết kết luận: binary có hỗ trợ không, platform có được vendor hỗ trợ không, generational mode có được chọn thật không và có đạt SLO không.

### Câu hỏi tự đánh giá

1. Vì sao Java 25 không bảo đảm mọi JDK distribution đều có Shenandoah?
2. JEP 521 thay đổi trạng thái generational mode như thế nào?
3. Vì sao chỉ bật `-XX:+UseShenandoahGC` chưa đủ để bật generational mode?
4. Tại sao Java 25 không cần `-XX:+UnlockExperimentalVMOptions` cho generational mode?
5. Vì sao Oracle JDK 25 và Red Hat build of OpenJDK 25 có thể có danh sách GC khác nhau?
6. Vì sao OS/CPU upstream support không đồng nghĩa vendor certified support?
7. Lệnh nào kiểm tra runtime binary có thể chọn Shenandoah?
8. Heuristics nào được hỗ trợ khi chạy generational mode?
9. Tại sao phải chạy probe bên trong container?
10. Vì sao low pause không đồng nghĩa không có CPU overhead?
11. Pacing và degenerated GC cho biết điều gì về allocation pressure?
12. Cần những metric nào để so sánh Shenandoah với G1/ZGC?

## 21. Checklist trước khi dùng trong production

- [ ] Đã xác định đúng Java 25 vendor, build và JVM implementation.
- [ ] Vendor xác nhận binary có Shenandoah.
- [ ] OS và CPU architecture nằm trong phạm vi hỗ trợ của package đang dùng.
- [ ] Không suy luận GC availability từ tên OpenJDK hoặc certified OS list.
- [ ] Probe `-XX:+UseShenandoahGC` chạy thành công trên binary triển khai.
- [ ] Probe `-XX:ShenandoahGCMode=generational` chạy thành công.
- [ ] Đã bỏ cờ unlock experimental cũ khỏi cấu hình JDK 25.
- [ ] Đã kiểm tra `ShenandoahGCMode=generational` thay vì mode mặc định `satb`.
- [ ] Không đặt heuristics ngoài `adaptive` cho generational mode.
- [ ] Không có GC selection flags xung đột.
- [ ] Heap và container memory limit có đủ headroom.
- [ ] GC logs được bật trong giai đoạn thử nghiệm.
- [ ] Đã kiểm tra young/old collections và các failure modes.
- [ ] Đã benchmark cùng workload với collector hiện tại.
- [ ] Đã so sánh latency, throughput, CPU, RSS và GC overhead.
- [ ] Có canary, rollback và phương án quay lại collector hiện tại.
- [ ] Có quy trình xác minh lại sau mỗi lần thay JDK vendor/update hoặc base image.

**Tiêu chí hoàn thành:** người học có thể kiểm tra chính xác bản phân phối, OS, CPU architecture và JVM build có hỗ trợ Shenandoah hay không; bật Generational Shenandoah bằng flags chính thức của JDK 25; xác minh mode qua flags/logs; và quyết định triển khai dựa trên benchmark cùng hỗ trợ của vendor. JEP 521 đã đưa generational mode thành product feature, nhưng khả năng sử dụng thực tế vẫn phụ thuộc binary và nền tảng cụ thể.

## 22. Tài liệu chính thức và nguồn đối chiếu

- [JEP 521 — Generational Shenandoah](https://openjdk.org/jeps/521): generational mode trở thành product feature trong JDK 25.
- [JEP 404 — Generational Shenandoah (Experimental)](https://openjdk.org/jeps/404): giai đoạn experimental trước JDK 25.
- [JEP 503 — Remove the 32-bit x86 Port](https://openjdk.org/jeps/503): giới hạn port 32-bit x86 trong JDK 25.
- [Red Hat build of OpenJDK 25 — Overview](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/getting_started_with_red_hat_build_of_openjdk_25/openjdk-overview): Red Hat xác nhận distribution bao gồm Shenandoah.
- [Red Hat build of OpenJDK 25 — Distribution selection](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/getting_started_with_red_hat_build_of_openjdk_25/openjdk-distribution-selection): nền tảng phân phối JDK 25 và giới hạn Windows.
- [Red Hat build of OpenJDK 25 — Release notes](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html-single/release_notes_for_red_hat_build_of_openjdk_25.0.1/index): cách bật generational mode và thay đổi từ JDK 24.
- [Azul Zulu 25 GA Release Notes](https://docs.azul.com/core/pdfs/25-ga/azul-zulu-ca-release-notes-25-ga-rev1.0.pdf): các bản sửa lỗi liên quan đến Shenandoah trong Zulu 25.
- [Oracle JDK 25 — Available Collectors](https://docs.oracle.com/en/java/javase/25/gctuning/available-collectors.html): tập collector được Oracle JDK 25 tài liệu hóa.
- [Oracle JDK 25 — Certified System Configurations](https://www.oracle.com/java/technologies/javase/products-doc-jdk25certconfig.html): nền tảng OS/CPU được Oracle chứng nhận; đây không phải bảng bảo đảm GC.
- [OpenJDK Shenandoah GC — Support Overview](https://wiki.openjdk.org/display/shenandoah/Support): trạng thái port OS/CPU upstream; cần đối chiếu với vendor package.

Khi nâng lên JDK mới hơn Java 25, kiểm tra lại mặc định mode, flags và supported platforms của release đó. Không áp dụng máy móc trạng thái JDK 25 cho các phiên bản tiếp theo.
