# Trạng thái experimental của JFR CPU-Time Profiling trong JDK 25

> **Chương:** CPU-time profiling
>
> **Phạm vi:** JDK 25, JEP 509 — **JFR CPU-Time Profiling (Experimental)**. Đây là một tính năng thử nghiệm có thể bật để đánh giá trong môi trường Linux. Bài học giải thích trạng thái hỗ trợ, khác biệt với `jdk.ExecutionSample`, cách thu thập và cách đọc dữ liệu để tránh coi kết quả thử nghiệm như một số đo CPU tuyệt đối.

## 1. Vì sao JFR cần CPU-time profiling?

JFR đã có method sampling để cho biết thread đang ở đâu trong lúc chạy. Tuy nhiên, **thời gian thực thi (wall-clock/execution time) và thời gian CPU (CPU time) là hai đại lượng khác nhau**:

- Một method tính toán ma trận có thể chạy liên tục trên CPU. Wall-clock time và CPU time của nó thường gần nhau.
- Một method gọi dịch vụ HTTP có thể mất 800 ms vì chờ mạng nhưng chỉ tiêu thụ vài ms CPU. Wall-clock time cao không có nghĩa method đó đốt nhiều CPU.
- Một ứng dụng dùng JNI hoặc Foreign Function & Memory API có thể tiêu thụ CPU trong native code. Method sampling truyền thống của JFR không phản ánh đầy đủ các frame native theo cách của CPU-time sampler mới.

JEP 509 bổ sung event `jdk.CPUTimeSample` để lấy mẫu theo **CPU time của từng thread** trên Linux. Event này có thể ghi nhận stack khi thread đang thực thi Java hoặc native code, nhờ đó giúp tìm method thực sự tiêu thụ CPU trong những tình huống mà thời gian chờ I/O làm sai lệch cách đọc profile.

Tính năng này bổ sung một góc nhìn cho JFR hiện có. Nó không thay thế các event `jdk.ExecutionSample`, `jdk.CPULoad`, `jdk.ThreadCPULoad` hay các công cụ đo CPU ở cấp hệ điều hành.

## 2. Trạng thái của JEP 509 trong Java 25

**Trạng thái trong JDK 25: Experimental.**

**JFR CPU-Time Profiling là tính năng experimental trong JDK 25.** Oracle ghi rõ trạng thái này trong tài liệu các thay đổi của JDK 25. Tài liệu migration của Oracle JDK 26 (tháng 3/2026), ở phần tóm tắt các thay đổi của JDK 25, vẫn ghi nhận CPU-Time Profiling là experimental; vì vậy không nên coi đây là một API đã ổn định chỉ vì JEP 509 đã được tích hợp vào bản phát hành.

Các hệ quả thực tế:

1. Event liên quan được đánh dấu bằng annotation `@Experimental`.
2. Cấu trúc event, cách lấy mẫu hoặc cách cấu hình có thể thay đổi giữa các bản JDK.
3. Công cụ hiển thị JFR có thể ẩn event experimental theo mặc định hoặc yêu cầu người dùng bật hiển thị.
4. Tính năng chỉ có trên Linux trong JDK 25; không giả định lệnh tương tự sẽ hoạt động trên Windows hoặc macOS.
5. Event bị tắt mặc định. Muốn thử phải bật rõ ràng trong recording.

Đây là **JFR event experimental**, không phải một tùy chọn VM experimental thông thường. Không cần thêm `-XX:+UnlockExperimentalVMOptions` để bật event. Chỉ cần cấu hình `jdk.CPUTimeSample#enabled=true` trong recording.

Nếu ứng dụng cần một cơ chế profiling ổn định cho mọi nền tảng, tiếp tục dùng các event JFR đã được hỗ trợ rộng rãi và công cụ profiling đã được tổ chức phê duyệt. Chỉ bật JEP 509 trong thử nghiệm có kiểm soát, sau khi chấp nhận rõ rủi ro thay đổi.

## 3. CPUTimeSample khác ExecutionSample như thế nào?

| Đặc điểm | `jdk.ExecutionSample` | `jdk.CPUTimeSample` |
| --- | --- | --- |
| Cách lấy mẫu | Theo chu kỳ thời gian thực của method sampler | Theo lượng CPU time thread đã tiêu thụ |
| Phạm vi code | Chủ yếu stack của thread đang chạy Java code | Stack của thread chạy Java hoặc native code |
| Thread chờ I/O/lock | Không phải mục tiêu lấy mẫu khi thread không chạy Java code | Không phát sinh CPU time trong lúc chờ; vì vậy không được xem như thời gian chờ |
| Nền tảng trong JDK 25 | Có trên các nền tảng JDK hỗ trợ JFR | Linux-only |
| Trạng thái | Event JFR hiện hành | Experimental |
| Cấu hình mặc định | Được bật trong các recording profile chuẩn | Tắt mặc định, cần opt-in |

`ExecutionSample` trả lời câu hỏi: *Trong các lần lấy mẫu, chương trình thường đang chạy ở method nào?* `CPUTimeSample` trả lời gần hơn với câu hỏi: *Khi thread thực sự tiêu thụ CPU, stack nào xuất hiện trong các lần lấy mẫu theo CPU time?*

Ví dụ, hai method sau có thời gian hoàn tất gần nhau:

- `oneSlowRequest()` gửi một request và chờ phản hồi lâu.
- `tenFastRequests()` gửi mười request nhỏ, xử lý nhiều dữ liệu hơn nhưng hoàn tất trong khoảng thời gian tương tự.

Execution-time profile có thể cho thấy cả hai chiếm thời gian tương đương. CPU-time profile có thể cho thấy `tenFastRequests()` dùng nhiều CPU hơn vì thực hiện nhiều công việc tính toán hơn. Đây là lý do hữu ích để có thêm góc nhìn CPU time.

**Lưu ý:** `CPUTimeSample` vẫn là sampling. Nó không đo và cộng chính xác từng chu kỳ CPU cho từng method như một bộ đếm phần cứng toàn diện. Hãy diễn giải số sample như bằng chứng thống kê, kết hợp với metric và workload thật.

## 4. Cơ chế hoạt động ở mức khái niệm

JDK 25 sử dụng cơ chế CPU timer của Linux để tạo yêu cầu lấy mẫu theo CPU time. JFR nhận yêu cầu, thu thập stack an toàn bằng cơ chế cooperative stack walking liên quan tới JEP 518, rồi ghi event `jdk.CPUTimeSample`.

~~~mermaid
flowchart TD
    A["Thread chạy Java hoặc native code trên Linux"] --> B["CPU time của thread tăng"]
    B --> C["Linux CPU timer phát yêu cầu lấy mẫu"]
    C --> D["JFR yêu cầu thu thập stack"]
    D --> E["Cooperative stack walking tại safepoint"]
    E --> F["Ghi jdk.CPUTimeSample"]
    F --> G["File .jfr"]
    G --> H["jfr view / JDK Mission Control"]
~~~

Điểm khác biệt là thời điểm lấy mẫu được gắn với **CPU time đã tiêu thụ**, không chỉ là một khoảng thời gian trên đồng hồ. Thread bị block chờ I/O không tiêu thụ CPU trong thời gian chờ nên không liên tục tạo sample như một thread đang tính toán.

JEP 518 giúp JFR đi bộ stack tại safepoint an toàn hơn và giảm sai lệch safepoint bias. Dù vậy, event CPU-time vẫn có field `biased` để người phân tích nhận diện những sample còn gắn với safepoint bias.

## 5. Các event liên quan và ý nghĩa từng field

### 5.1. `jdk.CPUTimeSample`

Event này ghi một lần lấy mẫu CPU-time. Trong JDK 25, các field chính gồm:

| Field | Ý nghĩa | Khi phân tích |
| --- | --- | --- |
| `eventThread` | Thread được lấy mẫu | Nhóm sample theo thread để xem thread nào đang tiêu thụ CPU. |
| `stackTrace` | Stack trace tại thời điểm lấy mẫu; có thể không có | Tìm method và chuỗi lời gọi liên quan. |
| `failed` | Cho biết thao tác lấy stack có thất bại hay không | Nếu `true`, không diễn giải event đó như một stack thành công. |
| `samplingPeriod` | CPU-time sampling period thực tế | Kiểm tra tần suất lấy mẫu thực tế. |
| `biased` | Cho biết sample có safepoint-biased hay không | Xem mức ảnh hưởng của bias khi đánh giá độ tin cậy. |

Nếu `failed=true`, stack trace có thể là `null`. Không loại bỏ thông tin này khi đánh giá chất lượng recording; tỷ lệ failed sample cao có thể làm profile thiếu đại diện.

### 5.2. `jdk.CPUTimeSamplesLost`

JDK 25 còn có event `jdk.CPUTimeSamplesLost`, ghi số sample bị mất. Bộ lấy mẫu dùng hàng đợi có giới hạn; nếu không xử lý kịp, một số sample có thể bị mất.

Field `lostSamples` cho biết số sample bị mất được báo cáo trong event. Khi xem profile, phải xét cả:

- Tổng số sample thành công.
- Sample thất bại khi lấy stack.
- Sample có safepoint bias.
- Sample bị mất.

Một flame graph đẹp nhưng có nhiều sample thất bại hoặc bị mất vẫn có thể thiếu phần quan trọng của workload.

## 6. Bật CPU-time profiling khi khởi động JVM

Ví dụ tối thiểu trên Linux với JDK 25:

~~~bash
java -XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,filename=cpu-time.jfr -jar checkout-service.jar
~~~

Tùy chọn `jdk.CPUTimeSample#enabled=true` bật event trong recording. File `cpu-time.jfr` chứa các sample được thu thập khi ứng dụng chạy.

Có thể thu đồng thời execution-time sample để đối chiếu:

~~~bash
java -XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,jdk.ExecutionSample#enabled=true,filename=cpu-and-execution.jfr -jar checkout-service.jar
~~~

Hai event có thể được thu cùng recording; bật CPU-time event không tự tắt hoặc thay đổi ý nghĩa của `jdk.ExecutionSample`.

Nếu cần một phiên thử ngắn, đặt thời lượng:

~~~bash
java -XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,duration=2m,filename=cpu-time-2m.jfr -jar checkout-service.jar
~~~

Không bật event trên production chỉ để “xem thử”. Hãy chạy một workload đại diện trên môi trường Linux thử nghiệm trước, kiểm tra event count, overhead và sample quality.

## 7. Bật event cho JVM đang chạy bằng custom JFC

Nếu ứng dụng đã chạy, có thể tạo file JFC riêng để bật event rồi dùng `jcmd` bắt đầu recording.

Tạo cấu hình dựa trên `profile.jfc`:

~~~bash
jfr configure --input profile.jfc --output cpu-time-profile.jfc jdk.CPUTimeSample#enabled=true jdk.CPUTimeSample#throttle=500/s
~~~

Sau đó attach vào PID của JVM:

~~~bash
jcmd <pid> JFR.start name=cpu-time-profile settings=cpu-time-profile.jfc duration=2m filename=cpu-time-profile.jfr
~~~

Kiểm tra recording:

~~~bash
jcmd <pid> JFR.check
~~~

Khi hết thời lượng, recording được ghi ra file. Nếu muốn dừng sớm, dùng `JFR.stop` và chỉ định `filename` để bảo toàn dữ liệu:

~~~bash
jcmd <pid> JFR.stop name=cpu-time-profile filename=cpu-time-profile-final.jfr
~~~

Giữ custom JFC cùng hồ sơ thử nghiệm để có thể tái lập kết quả. Không chỉnh trực tiếp `default.jfc` hoặc `profile.jfc` trong thư mục JDK.

## 8. Điều chỉnh throttle để kiểm soát số event

`jdk.CPUTimeSample` có setting `throttle`. Có thể cấu hình theo một trong hai cách:

| Kiểu giá trị | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Khoảng CPU-time | Lấy mẫu mỗi thread sau một khoảng CPU time đã tiêu thụ | `10ms` |
| Giới hạn tốc độ event | Giới hạn tổng tốc độ phát event | `500/s` |

Với `10ms`, một thread CPU-bound có thể tạo tối đa khoảng 100 sample mỗi giây. Khi có nhiều hardware thread, tổng event rate có thể tăng theo số thread đang thực sự dùng CPU. Với `500/s`, sampler điều chỉnh khoảng lấy mẫu để giới hạn tổng số event gần mức 500 event mỗi giây.

JDK 25 cung cấp các giá trị cấu hình mặc định khác nhau giữa recording templates:

| Template | `jdk.CPUTimeSample#enabled` | `throttle` |
| --- | --- | --- |
| `default.jfc` | `false` | `500/s` |
| `profile.jfc` | `false` | `10ms` |

Cả hai template đều để event tắt. Bật event là lựa chọn riêng của người vận hành. Với lần thử đầu tiên, giới hạn tốc độ event bằng một giá trị như `500/s` giúp tránh tạo quá nhiều dữ liệu trên máy có nhiều hardware thread. Nếu cần độ phân giải cao hơn, hãy tăng dần mức lấy mẫu trong một workload có kiểm soát.

Không coi `throttle` là cam kết overhead cố định. Số event thực tế còn phụ thuộc số thread CPU-bound, phần cứng, thời gian recording và khả năng lấy stack.

## 9. Đọc recording bằng công cụ JFR

Trước hết kiểm tra file:

~~~bash
jfr summary cpu-time.jfr
~~~

Xem danh sách view có sẵn:

~~~bash
jfr view all-views cpu-time.jfr
~~~

Các bản JDK 25 có view dành cho CPU-time profiling:

~~~bash
jfr view cpu-time-hot-methods cpu-time.jfr
jfr view cpu-time-statistics cpu-time.jfr
~~~

`cpu-time-hot-methods` xếp các method xuất hiện nhiều nhất ở đỉnh stack trong CPU-time samples. `cpu-time-statistics` tổng hợp sample thành công, sample thất bại, sample biased, tổng số sample và sample bị mất.

Có thể xem trực tiếp event:

~~~bash
jfr print --events jdk.CPUTimeSample,jdk.CPUTimeSamplesLost cpu-time.jfr
~~~

Nếu view không có trong bản JDK đang dùng, kiểm tra bằng `jfr view all-views` và `jfr metadata`. Không giả định mọi vendor hoặc bản cập nhật đều có cùng danh sách view.

### Cách diễn giải kết quả

1. Bắt đầu từ `cpu-time-hot-methods` để tìm các method có nhiều sample.
2. Mở stack trace của method đứng đầu để hiểu caller và công việc liên quan.
3. Xem `cpu-time-statistics` để đánh giá failed, biased và lost samples.
4. Nhóm theo `eventThread` nếu cần tìm thread tiêu thụ CPU.
5. Đối chiếu với CPU utilization, request throughput, latency và workload trong cùng khoảng thời gian.

Số sample là ước lượng thống kê. Không diễn giải `Percent` trong view như phần trăm CPU của toàn máy hoặc phần trăm CPU của toàn process nếu view không định nghĩa mẫu số như vậy.

## 10. Đánh giá chất lượng profile

Trước khi dùng profile để quyết định tối ưu, kiểm tra chất lượng dữ liệu:

| Dấu hiệu | Ý nghĩa | Hành động |
| --- | --- | --- |
| `failed` nhiều | Nhiều lần lấy sample không thu được stack | Kiểm tra workload, thời gian recording và JDK/provider; không coi profile là đầy đủ. |
| `biased` nhiều | Nhiều stack gắn với safepoint frame thay vì vị trí lấy mẫu dự kiến | Xem xét bias khi đọc hot method; đối chiếu recording khác. |
| `lostSamples` tăng | Sampler đã mất event | Giảm event rate bằng `throttle` thấp hơn hoặc rút ngắn khoảng thử. |
| Tổng sample quá ít | Workload quá ngắn hoặc CPU không bận | Thu lại trong thời gian workload đại diện và đủ dài. |
| Hot method thay đổi mạnh giữa các lần chạy | Workload hoặc sample count không ổn định | Chuẩn hóa input, tải đồng thời, thời gian đo và cấu hình. |

Không đặt ngưỡng pass/fail phổ quát cho failed, biased hoặc lost samples. Hãy xác định ngưỡng theo mục tiêu, tải thực tế và mức độ chấp nhận sai số của phép điều tra.

## 11. Thử nghiệm so sánh CPU time với execution time

Tạo một ứng dụng thử nghiệm có hai đường xử lý:

- Một đường tính toán CPU-bound, ví dụ xử lý mảng lớn trong vòng lặp.
- Một đường chờ I/O, ví dụ gọi một HTTP endpoint chậm rồi xử lý ít dữ liệu.

Thu cùng recording với cả hai event:

~~~bash
java -XX:StartFlightRecording:jdk.CPUTimeSample#enabled=true,jdk.ExecutionSample#enabled=true,filename=compare-sampling.jfr -jar profiling-lab.jar
~~~

Phân tích:

~~~bash
jfr view cpu-time-hot-methods compare-sampling.jfr
jfr view cpu-time-statistics compare-sampling.jfr
jfr print --events jdk.ExecutionSample compare-sampling.jfr
~~~

**Câu hỏi cần trả lời:**

1. Method nào đứng đầu trong CPU-time profile?
2. Method chờ I/O xuất hiện như thế nào trong execution-time profile?
3. Kết quả có thay đổi khi tăng số request đồng thời không?
4. Có bao nhiêu sample failed, biased hoặc lost?
5. Khi thay `throttle=500/s` bằng `throttle=10ms`, event volume và thời gian thu thập thay đổi ra sao?

Mục tiêu là hiểu sự khác nhau giữa thời gian thread thực thi và lượng CPU thread tiêu thụ. Không dùng một lần chạy duy nhất để kết luận method nào luôn là bottleneck.

## 12. Giới hạn và rủi ro của tính năng experimental

### Phạm vi nền tảng

- Chỉ dùng được trên Linux trong JDK 25.
- Không giả định hỗ trợ tương đương trên Windows, macOS hoặc các runtime không cung cấp cùng HotSpot implementation.
- Kiểm tra bản JDK vendor và patch level đang triển khai trước khi chạy.

### Độ ổn định và khả năng tương thích

- JFR event được đánh dấu `@Experimental`; cấu trúc hoặc hành vi có thể thay đổi.
- Công cụ đọc JFR có thể ẩn event experimental theo mặc định.
- Không thiết kế format lưu trữ dài hạn hoặc hợp đồng giữa hệ thống dựa trên event này như thể schema đã ổn định.
- Không phụ thuộc vào `cpu-time-hot-methods` hay `cpu-time-statistics` nếu chưa xác minh chúng tồn tại trong bản JDK đích.

### Chất lượng và chi phí đo

- Sampling là phương pháp thống kê, không phải phép đếm chính xác từng instruction hoặc CPU cycle của từng method.
- Event rate cao có thể làm recording lớn và tăng chi phí xử lý.
- Failed, biased và lost samples làm dữ liệu thiếu hoặc lệch.
- Kết quả chịu ảnh hưởng bởi workload, số hardware thread, JDK build và môi trường Linux.

Do đó, không bật CPU-time profiling như cấu hình always-on mặc định cho production Java 25. Nếu một incident cần thử nghiệm trên production, hãy giới hạn thời lượng và throttle, ghi nhận rủi ro, có phương án quay lại recording JFR thông thường và không dùng kết quả làm căn cứ duy nhất cho quyết định tối ưu.

## 13. Khi nào nên dùng và khi nào không?

| Tình huống | Lựa chọn |
| --- | --- |
| Muốn biết method Java nào thường xuất hiện khi thread chạy | Bắt đầu với `jdk.ExecutionSample` và `profile.jfc`. |
| Muốn phân biệt method tính toán CPU với method chủ yếu chờ I/O trên Linux | Có thể thử `jdk.CPUTimeSample` trong môi trường kiểm soát. |
| Cần profile ổn định trên nhiều hệ điều hành | Dùng các event JFR đã hỗ trợ rộng rãi hoặc công cụ profiling được hỗ trợ trên nền tảng đích. |
| Cần đo CPU utilization của process/máy | Dùng `jdk.CPULoad`, `jdk.ThreadCPULoad` và công cụ hệ điều hành; CPUTimeSample không thay thế các metric này. |
| Cần một hợp đồng event ổn định cho telemetry lâu dài | Không phụ thuộc vào event experimental. |
| Cần khảo sát native code trong một ứng dụng Linux | CPU-time profiling có thể hữu ích nếu JDK build hỗ trợ và chấp nhận trạng thái experimental. |

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không có `jdk.CPUTimeSample` trong file | Event chưa được bật hoặc runtime không hỗ trợ | Kiểm tra Linux/JDK build và setting `jdk.CPUTimeSample#enabled=true`. |
| Không thấy event trên Windows/macOS | Tính năng JDK 25 chỉ dành cho Linux | Dùng event sampling thông thường trên nền tảng đó. |
| `jfr view cpu-time-hot-methods` báo không có view | Bản JDK/vendor không cung cấp view đó | Chạy `jfr view all-views` hoặc dùng `jfr print`. |
| Không có stack trace | `failed=true` hoặc stack trace không thu được | Kiểm tra event fields và chất lượng recording; không diễn giải sample này như stack hợp lệ. |
| Có nhiều sample bị mất | Event rate cao hoặc sampler không theo kịp | Tăng throttle period hoặc giảm rate; thu ngắn hơn rồi so sánh. |
| Profile lệch nhiều | `biased` cao hoặc workload không đại diện | Kiểm tra statistics và chạy lại workload chuẩn hóa. |
| Thêm `-XX:+UnlockExperimentalVMOptions` nhưng vẫn không thấy event | Đang nhầm event experimental với VM option experimental | Bật event bằng `jdk.CPUTimeSample#enabled=true`; unlock VM options không thay thế setting này. |
| Công cụ GUI không hiển thị event | Viewer có thể ẩn event `@Experimental` | Kiểm tra cấu hình hiển thị experimental event hoặc dùng `jfr print`. |

## 15. Checklist thử nghiệm an toàn

- [ ] Xác nhận đang chạy JDK 25 trên Linux.
- [ ] Xác nhận vendor/build JDK có event `jdk.CPUTimeSample`.
- [ ] Hiểu rõ tính năng vẫn experimental; không xem là hợp đồng ổn định.
- [ ] Bật event rõ ràng bằng `jdk.CPUTimeSample#enabled=true`.
- [ ] Không thêm `-XX:+UnlockExperimentalVMOptions` như một bước bắt buộc.
- [ ] Đặt `throttle` phù hợp để giới hạn event volume.
- [ ] Chạy workload đại diện và thu đủ lâu để có sample hữu ích.
- [ ] Kiểm tra `jdk.CPUTimeSamplesLost`, `failed`, `biased` và `samplingPeriod`.
- [ ] Đối chiếu với `jdk.ExecutionSample`, metric CPU và dữ liệu hệ điều hành.
- [ ] Không dùng một flame graph hoặc một lần chạy làm kết luận duy nhất.
- [ ] Không bật always-on production nếu chưa chấp nhận rõ rủi ro experimental.
- [ ] Ghi lại JDK build, kernel/platform, JFC, throttle và thời gian đo để tái lập kết quả.

## 16. Tài liệu tham khảo

1. [JEP 509 — JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509): mục tiêu và trạng thái experimental của tính năng.
2. [Oracle — Significant Changes in JDK 25 Release](https://docs.oracle.com/en/java/javase/25/migrate/significant-changes-jdk-25.html): xác nhận CPU-Time Profiling trên Linux và trạng thái experimental trong JDK 25.
3. [Oracle — JDK Migration Guide 26](https://docs.oracle.com/en/java/javase/26/migrate/jdk-migration-guide.pdf): tài liệu migration tháng 3/2026 tiếp tục ghi nhận CPU-Time Profiling là experimental.
4. [JDK 25 JFR Event Reference — CPUTimeSample](https://sap.github.io/jfrevents/25.html): field, cấu hình `throttle`, event `CPUTimeSamplesLost` và phạm vi nền tảng của event trong JDK 25.
5. [JEP 518 — JFR Cooperative Sampling](https://openjdk.org/jeps/518): cơ chế cooperative stack walking hỗ trợ lấy mẫu stack an toàn.
6. [Oracle Java 25 — `jfr` Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): cách xem, in và tổng hợp recording.
7. [Oracle Java 25 — JFR API and Event Settings](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html): cấu trúc setting event dạng `event-name#setting-name`.
8. [Red Hat — JDK 25 Release Notes: JFR CPU-Time Profiling](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_red_hat_build_of_openjdk_25.0.1/openjdk25-features): event được đánh dấu `@Experimental` và không cần `-XX:+UnlockExperimentalVMOptions`.

**Ghi nhớ:** JEP 509 đưa một event CPU-time mới vào JFR của JDK 25, nhưng event này vẫn **experimental, Linux-only và tắt mặc định**. Hãy bật nó chỉ trong thử nghiệm có kiểm soát, giới hạn tốc độ sample, đọc cả failed/biased/lost samples và đối chiếu với metric khác. Đây là một góc nhìn bổ sung để tìm nơi tiêu thụ CPU; không phải bộ đếm CPU tuyệt đối hay nền tảng ổn định cho mọi ứng dụng.
