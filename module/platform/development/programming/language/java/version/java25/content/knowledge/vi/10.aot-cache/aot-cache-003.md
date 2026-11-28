# Quy trình huấn luyện và tạo cache với cơ chế dòng lệnh của JDK 25

## 1. Mục tiêu: biến một lần chạy đại diện thành AOT cache có thể tái sử dụng

Một ứng dụng Java thường phải tải, phân tích, liên kết và khởi tạo nhiều class khi JVM khởi động. Với dịch vụ lớn, phần công việc này có thể chiếm đáng kể thời gian trước khi ứng dụng sẵn sàng nhận request. Sau khi khởi động, JVM còn cần thu thập thông tin thực thi để JIT compiler nhận diện các method nóng và tối ưu hóa chúng.

**Ahead-of-Time (AOT) cache** cho phép chuyển một phần công việc sang giai đoạn chuẩn bị trước. Ứng dụng được chạy trong một lần **training** với workload đại diện; JVM ghi nhận các thông tin phù hợp, sau đó tạo file cache. Những lần chạy tiếp theo có thể nạp cache để giảm công việc lặp lại khi khởi động và cải thiện giai đoạn warm-up.

Java 25 làm quy trình này thuận tiện hơn qua **JEP 514 — Ahead-of-Time Command-Line Ergonomics**: một tùy chọn `-XX:AOTCacheOutput` có thể thực hiện training và assembly trong một invocation. **JEP 515 — Ahead-of-Time Method Profiling** mở rộng cache để lưu method execution profiles thu thập trong training, giúp JIT có thông tin sớm hơn khi ứng dụng chạy lại. https://openjdk.org/jeps/514 · https://openjdk.org/jeps/515

Bài thuộc chương **AOT cache** của module **JAVA_VERSION_JAVA25**. Nội dung tập trung vào **“Quy trình huấn luyện và tạo cache với cơ chế dòng lệnh của JDK 25”** và các điều kiện để cache được dùng đúng trên môi trường triển khai.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích training, assembly và production run.
2. Tạo cache bằng một lệnh `-XX:AOTCacheOutput` của Java 25.
3. Tách riêng training và assembly khi cần kiểm soát tài nguyên.
4. Chuẩn bị workload đại diện để cache phản ánh class loading và method hotness thực tế.
5. Dùng cache cho ứng dụng Java thường và Spring Boot executable JAR.
6. Kiểm tra cache được nạp thành công, đo lợi ích và xử lý lỗi tương thích.
7. Lập quy trình tái tạo cache mỗi khi artifact hoặc môi trường mục tiêu thay đổi.

## 2. AOT cache là gì và lưu những gì?

AOT cache là một container do HotSpot JVM tạo ra để lưu các artifacts có thể tái sử dụng giữa những lần chạy của cùng ứng dụng. Tính năng cache được giới thiệu ở JDK 24 qua JEP 483; Java 25 bổ sung trải nghiệm dòng lệnh và method profiling.

Trong Java 25, cache có thể chứa:

- Class data đã được đọc, phân tích, tải và liên kết.
- Các heap objects được chuẩn bị trong quá trình AOT.
- Method execution profiles được thu thập trong training, theo JEP 515.

Method profiles cung cấp thông tin về những method thường được gọi và hành vi thực thi đã quan sát. Khi ứng dụng chạy lại, JIT có thể tận dụng thông tin đó sớm hơn thay vì phải chờ thu thập đầy đủ profile mới bắt đầu các quyết định tối ưu hóa tương ứng.

**AOT cache không phải native executable.** JVM vẫn chạy bytecode, vẫn có JIT compiler và vẫn tiếp tục thu thập thống kê ở runtime. Cache chuyển một phần công việc sang giai đoạn trước; nó không thay JVM bằng một binary native như một quy trình native-image riêng.

~~~mermaid
flowchart LR
    A["Ứng dụng + JDK 25"] --> B["Training run"]
    B --> C["Ghi class data, heap objects, method profiles"]
    C --> D["Assembly"]
    D --> E["File app.aot"]
    E --> F["Production run"]
    F --> G["Khởi động/warm-up với cache"]
    G --> H["JIT tiếp tục tối ưu ở runtime"]
~~~

### AOT cache khác Spring AOT

Hai khái niệm thường bị nhầm:

| Khái niệm | Thời điểm và tác dụng |
| --- | --- |
| **Spring AOT processing** | Build-time: phân tích Spring ApplicationContext và sinh mã/hints để đơn giản hóa bootstrap, reflection hoặc cấu hình |
| **JVM AOT cache** | Training/assembly: JVM ghi cache từ lần chạy đại diện để tái sử dụng khi chạy lại |
| **Native image** | Biên dịch ứng dụng thành executable native bằng công cụ/runtime tương ứng; không phải file `.aot` của HotSpot |

Một ứng dụng Spring có thể sử dụng Spring AOT và JVM AOT cache theo các quy trình riêng, nhưng bật một cơ chế không có nghĩa cơ chế còn lại tự động được bật. Bài này tập trung vào **JVM AOT cache của JDK 25**.

## 3. Ba giai đoạn: training, assembly và production

Quy trình khái niệm có ba giai đoạn.

### 3.1. Training — huấn luyện

Chạy ứng dụng bằng JDK mục tiêu với workload có tính đại diện. JVM quan sát class loading/linking, object initialization và method execution; thông tin được ghi vào cấu hình AOT hoặc dùng làm đầu vào cho việc tạo cache.

Mục tiêu không phải chạy mọi test có thể có. Mục tiêu là mô phỏng những luồng quan trọng mà ứng dụng sẽ thực thi trong production, ví dụ:

- Khởi động application context.
- Nhận một nhóm request thường dùng.
- Chạy các đường nghiệp vụ chính.
- Đi qua những nhánh xử lý có method nóng.
- Khởi tạo client, serializer, repository hoặc component cần thiết trong vận hành thực tế.

### 3.2. Assembly — tạo cache

JVM sử dụng dữ liệu training để tạo file AOT cache, thường có đuôi `.aot`. Giai đoạn này không chạy logic nghiệp vụ của ứng dụng; nó xử lý thông tin đã thu thập để tạo artifacts có thể nạp về sau.

### 3.3. Production — chạy với cache

Khởi động cùng ứng dụng, JDK, hệ điều hành, kiến trúc CPU và cấu hình tương thích, đồng thời truyền đường dẫn cache qua `-XX:AOTCache`.

Nếu cache không dùng được trong chế độ mặc định `auto`, JVM có thể tiếp tục chạy mà không dùng cache. Ứng dụng phải đúng và hoạt động bình thường **ngay cả khi cache không được nạp**; cache là tối ưu hóa, không phải dữ liệu nghiệp vụ bắt buộc.

## 4. Cơ chế dòng lệnh mới trong JDK 25: một lệnh tạo cache

Cách ngắn nhất để training và tạo cache:

~~~bash
java -XX:AOTCacheOutput=app.aot \
     -cp app.jar com.example.App
~~~

Trong đó:

- `-XX:AOTCacheOutput=app.aot` chỉ định file cache đầu ra.
- `-cp app.jar` chỉ định classpath của ứng dụng.
- `com.example.App` là main class.
- Các tham số phía sau main class được truyền cho ứng dụng.

Nếu không chỉ định `-XX:AOTMode`, JDK 25 dùng chế độ mặc định `auto`. Khi có `-XX:AOTCacheOutput`, JVM chuyển sang training/record; sau khi training kết thúc, JVM khởi chạy tiến trình JVM thứ hai để thực hiện assembly và ghi `app.aot`.

**Một invocation ở phía người vận hành không có nghĩa chỉ một JVM process nội bộ.** Cơ chế mới tự điều phối phần training và assembly; đó là thay đổi ergonomics của JEP 514.

### Ví dụ ứng dụng ngắn

~~~java
package com.example;

import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class App {

    public static void main(String[] args) {
        String mode = args.length == 0 ? "default" : args[0];

        List<String> values = IntStream.range(0, 1000)
                .mapToObj(i -> "item-" + i)
                .toList();

        String result = values.stream()
                .filter(value -> value.length() > 6)
                .collect(Collectors.joining(","));

        System.out.println("mode=" + mode);
        System.out.println("items=" + values.size());
        System.out.println("resultLength=" + result.length());
    }
}
~~~

Biên dịch và tạo JAR bằng toolchain Java 25 theo quy trình build của dự án, sau đó chạy lệnh:

~~~bash
java -XX:AOTCacheOutput=app.aot \
     -cp app.jar com.example.App training
~~~

Khi ứng dụng kết thúc bình thường, JVM hoàn tất training và tạo cache. Với chương trình demo ngắn, đây là cách dễ quan sát nhất. Với server chạy lâu dài, cần giữ process hoạt động trong lúc gửi workload rồi kết thúc training có kiểm soát; phần 8 trình bày cách làm.

### Nếu cần lưu file cấu hình training rõ ràng

Có thể kết hợp `-XX:AOTConfiguration` với `-XX:AOTCacheOutput`:

~~~bash
java -XX:AOTConfiguration=app.aotconfig \
     -XX:AOTCacheOutput=app.aot \
     -cp app.jar com.example.App training
~~~

Cách này giữ file cấu hình training ở đường dẫn xác định thay vì để JVM sử dụng tên tạm. Khi dùng chế độ mặc định `auto`, `AOTCacheOutput` vẫn kích hoạt quy trình record và assembly; `AOTConfiguration` chỉ định nơi lưu dữ liệu cấu hình.

Không dùng đồng thời `-XX:AOTCache` và `-XX:AOTCacheOutput` trong cùng invocation; hai tùy chọn có vai trò khác nhau.

## 5. Hiểu các chế độ AOT trong JDK 25

JDK 25 cung cấp các chế độ sau qua `-XX:AOTMode`:

| Mode | Mục đích | Ứng dụng chính |
| --- | --- | --- |
| `auto` | Tự quyết định record, dùng cache hoặc chạy không cache | Mặc định, phù hợp phần lớn quy trình |
| `off` | Tắt AOT cache | Baseline hoặc điều tra không dùng cache |
| `record` | Chạy ứng dụng để ghi training data | Giai đoạn training riêng |
| `create` | Assembly từ file cấu hình đã ghi | Tạo cache tách khỏi training |
| `on` | Bắt buộc nạp cache, lỗi nếu không thể dùng | Kiểm tra fail-fast |

### Quy tắc của `auto`

- Nếu có `-XX:AOTCacheOutput=...`, JVM chuyển sang training/record và tiếp tục assembly.
- Nếu không có cache output nhưng có thể nạp cache được chỉ định, JVM dùng cache.
- Nếu không có cache phù hợp, JVM chạy không cache.

Đây là hành vi hữu ích khi ứng dụng có thể được khởi chạy từ nhiều môi trường và việc nạp cache không phải điều kiện để phục vụ nghiệp vụ.

### `on` dành cho kiểm chứng

Khi kiểm tra cache, có thể dùng:

~~~bash
java -XX:AOTCache=app.aot \
     -XX:AOTMode=on \
     -cp app.jar com.example.App
~~~

Nếu cache không tương thích, JVM báo lỗi thay vì âm thầm tiếp tục. Dùng chế độ này trong pipeline kiểm tra hoặc môi trường staging để phát hiện cache không được sử dụng như dự kiến. Với production, `auto` thường an toàn hơn vì ứng dụng có thể chạy tiếp nếu cache không dùng được.

## 6. Quy trình tách riêng training và assembly

JDK 25 vẫn hỗ trợ tách rõ các bước. Cách này hữu ích khi training cần một máy gần với production, nhưng assembly cần nhiều RAM/CPU hơn; hoặc khi muốn lưu, review và tái sử dụng file cấu hình giữa các job.

### Bước 1 — Training

~~~bash
java -XX:AOTMode=record \
     -XX:AOTConfiguration=app.aotconfig \
     -cp app.jar com.example.App training
~~~

JVM chạy ứng dụng và ghi dữ liệu training vào `app.aotconfig`. Ứng dụng phải thực sự chạy workload cần đại diện; với server, giữ process trong lúc gửi traffic và dừng training theo cách có kiểm soát.

### Bước 2 — Assembly

~~~bash
java -XX:AOTMode=create \
     -XX:AOTConfiguration=app.aotconfig \
     -XX:AOTCache=app.aot \
     -cp app.jar
~~~

Ở mode `create`, JVM đọc file cấu hình và ghi cache vào đường dẫn `app.aot`. Ứng dụng không chạy logic main trong giai đoạn assembly.

### Bước 3 — Production

~~~bash
java -XX:AOTCache=app.aot \
     -cp app.jar com.example.App
~~~

JVM nạp cache và khởi động ứng dụng. Với chế độ mặc định `auto`, nếu cache không tương thích, JVM có thể tiếp tục mà không dùng cache.

### So sánh hai cách

| Tiêu chí | Một lệnh `AOTCacheOutput` | Tách `record` và `create` |
| --- | --- | --- |
| Số bước vận hành | Gọn | Nhiều bước |
| File config | Có thể dùng file tạm hoặc chỉ định rõ | Chỉ định rõ |
| Tài nguyên assembly | Cùng môi trường quy trình một lệnh | Có thể chuyển assembly sang job riêng |
| Dễ tích hợp CI | Cao với ứng dụng ngắn và môi trường đủ tài nguyên | Cao khi cần pipeline nhiều stage |
| Phù hợp | Demo, batch, pipeline đơn giản | Server dài hạn, build farm hoặc giới hạn RAM |

## 7. Chọn workload training: phần quan trọng nhất

Cache tốt phụ thuộc vào việc lần training có phản ánh đúng ứng dụng production hay không. Nếu chỉ chạy startup rồi thoát, cache có thể phản ánh class loading và initialization nhưng thiếu thông tin về method được thực thi thường xuyên.

Java 25 bổ sung method profiling qua JEP 515. Vì vậy, nếu mục tiêu là cải thiện cả warm-up, hãy cho ứng dụng thực hiện một phần **production-like workflow** trong training.

### Workload nên có

| Loại ứng dụng | Luồng nên mô phỏng |
| --- | --- |
| REST API | Startup, authentication, endpoint phổ biến, validation, serialization |
| Batch | Đọc input mẫu, xử lý các bước chính, ghi output test |
| Messaging consumer | Khởi tạo listener, deserialize, xử lý message mẫu |
| CLI | Các lệnh và chế độ sử dụng phổ biến |
| Spring Boot | ApplicationContext, request nghiệp vụ, client, repository và serializer |
| Worker nền | Scheduler/task chính, queue polling và thao tác dữ liệu đại diện |

### Tránh training chỉ với startup nếu muốn method profiles

Một training run chỉ làm JVM khởi động, tạo context rồi thoát có thể hữu ích để chuẩn bị startup artifacts. Nhưng nó không đại diện cho các method nóng trong quá trình xử lý request hoặc batch.

Với JDK 25, nên:

1. Khởi động ứng dụng bằng `-XX:AOTCacheOutput`.
2. Chờ ứng dụng sẵn sàng.
3. Gửi workload đại diện với tần suất và concurrency hợp lý.
4. Chạy đủ lâu để các đường nghiệp vụ quan trọng được thực thi.
5. Kết thúc training và tạo cache.
6. Đánh giá method profiles có giúp warm-up của workload thật hay không.

Không cần chạy vô hạn hoặc mô phỏng toàn bộ production. Cần chọn một tập luồng đại diện có thể lặp lại và có dữ liệu test an toàn.

### Tránh training quá rộng

Nếu training chạy cả test framework, test discovery, mock infrastructure và các nhánh không có trong production, cache có thể chứa nhiều class hoặc dữ liệu không cần thiết. Điều này làm tăng kích thước cache và giảm hiệu quả.

Có thể dùng integration test hoặc synthetic workload để kích hoạt các luồng cần thiết. Khi mock external dependencies, nhớ rằng các mock có thể làm tải thêm class không có trong production; chỉ giữ chúng nếu lợi ích về an toàn và khả năng tái lập lớn hơn tác động đó.

## 8. Training cho ứng dụng server chạy lâu dài

Ứng dụng server thường không tự kết thúc sau một request. Với một lệnh:

~~~bash
java -XX:AOTCacheOutput=service.aot \
     -cp service.jar com.example.ServiceApplication
~~~

JVM bắt đầu training và giữ ứng dụng chạy. Sau khi workload đại diện hoàn tất, dừng ứng dụng bằng quy trình shutdown được kiểm soát. Khi JVM kết thúc, phần assembly của quy trình `AOTCacheOutput` được thực hiện.

Trong môi trường cần giữ server tiếp tục chạy sau khi kết thúc recording, có thể dùng `jcmd` để dừng AOT recording:

~~~bash
jcmd -l
jcmd <pid> AOT.end_recording
~~~

`<pid>` là process ID của JVM đang training. Lệnh `AOT.end_recording` kết thúc recording và ghi kết quả vào file đã chỉ định qua `-XX:AOTConfiguration` và/hoặc `-XX:AOTCacheOutput`. Quyền truy cập attach và cấu hình JVM phải cho phép dùng `jcmd`.

Với server production, không dùng trực tiếp traffic có side effects không kiểm soát để training. Nên chọn môi trường staging hoặc bản triển khai cô lập có dữ liệu giả, database sandbox và external integrations được mock/stub.

## 9. Spring Boot executable JAR: chuẩn bị layout trước khi training

Với Spring Boot executable JAR, nên sử dụng khả năng unpacking/extraction của Spring Boot. Layout này giúp classpath ở dạng các JAR riêng biệt và phù hợp hơn với các yêu cầu class loading của AOT cache.

Ví dụ với phiên bản Spring Boot có hỗ trợ tools jarmode:

~~~bash
java -Djarmode=tools -jar my-app.jar \
     extract --destination application
~~~

Sau khi extract, chuyển tới thư mục:

~~~bash
cd application
~~~

Từ đây chạy ứng dụng bằng launcher JAR trong layout đã extract và tạo cache:

~~~bash
java -XX:AOTCacheOutput=app.aot \
     -jar my-app.jar
~~~

Lưu ý:

- Tên file JAR trong thư mục extract tùy artifact đầu vào; dùng đúng tên file được tạo ra.
- Cache cần được sử dụng cùng layout extracted tương ứng; chỉ thêm `-XX:AOTCache` khi chạy lại uber JAR ban đầu sẽ không có tác dụng như mong đợi.
- Dùng cùng JDK 25, classpath và timestamps của các JAR.
- Tạo lại cache khi artifact/dependencies thay đổi.

### Biến thể chỉ training startup

Spring hỗ trợ cho ApplicationContext tự kết thúc ngay sau refresh:

~~~bash
java -XX:AOTCacheOutput=app.aot \
     -Dspring.context.exit=onRefresh \
     -jar my-app.jar
~~~

Cách này có thể tạo cache sau khi singleton không lazy đã được khởi tạo. Tuy nhiên, nó **chỉ mô phỏng giai đoạn khởi động**; không chạy phần lớn request/business methods. Nếu muốn tận dụng method profiles của JEP 515, hãy training với một phần workflow gần production thay vì chỉ dùng `spring.context.exit=onRefresh`.

### Chạy Spring Boot với cache

Sau khi có `app.aot`, khởi động extracted application:

~~~bash
java -XX:AOTCache=app.aot \
     -jar my-app.jar
~~~

Spring Boot và JVM vẫn cần cùng runtime/dependencies tương thích. Kiểm tra log JVM để xác nhận cache được nạp thay vì chỉ dựa vào việc ứng dụng khởi động thành công.

## 10. Điều kiện tương thích giữa training và production

AOT cache gắn với ứng dụng và môi trường cụ thể. Không nên xem file `.aot` là artifact phổ quát có thể dùng với bất kỳ JAR hoặc máy nào.

Các điều kiện quan trọng:

| Yếu tố | Yêu cầu |
| --- | --- |
| Ứng dụng | Cùng ứng dụng và trạng thái artifact tương ứng |
| JDK | Cùng JDK release; nên dùng cùng vendor/build trong pipeline |
| Hệ điều hành | Cùng OS family/môi trường tương thích |
| CPU | Cùng kiến trúc CPU |
| Classpath/module path | Phải tương thích với training; giữ cùng thứ tự JAR |
| JAR timestamps | Giữ nguyên timestamps giữa training và production |
| JVM options | Tránh các tùy chọn làm thay đổi class loading hoặc instrumentation không tương thích |
| Agents | Không dùng JVMTI agents sửa bootstrap/system class loader theo cách không tương thích |

Với classpath, tài liệu Spring Framework khuyến nghị dùng danh sách JAR cụ thể thay vì thư mục hoặc wildcard; khi sử dụng cache, classpath nên giữ cùng thứ tự như training. Production có thể thêm các JAR hoặc thư mục ở cuối trong trường hợp được hỗ trợ, nhưng những thành phần thêm đó không được cache theo training cũ.

**Không tạo cache từ build A rồi dùng cho build B** chỉ vì tên JAR giống nhau. Thay đổi code, dependency, JDK, OS hoặc kiến trúc có thể làm cache không còn phù hợp. Trong CI/CD, nên tạo cache từ đúng artifact sẽ được phát hành và gắn cache với cùng version/digest của artifact.

### Một số JVM options/agent có thể làm cache không dùng được

Một số cấu hình chẩn đoán hoặc agent thay đổi class loading có thể làm cache không tương thích. Oracle mô tả những trường hợp liên quan đến JVMTI, thay đổi module path hoặc các tùy chọn patch/upgrade module. Khi cache không load, hãy xem log AOT và kiểm tra option differences thay vì cố ép JVM sử dụng cache.

## 11. Giới hạn GC của AOT cache trong JDK 25

Khi sử dụng AOT cache của **JDK 25**, cần lưu ý giới hạn hỗ trợ collector: cơ chế AOT object caching ở JDK 24/25 chưa hỗ trợ **ZGC**. Nếu workload đang dùng ZGC, không nên giả định chỉ cần thêm `-XX:AOTCache` là cache sẽ hoạt động.

Giới hạn này được thay đổi ở **JDK 26** với JEP 516 — Ahead-of-Time Object Caching with Any GC. Vì vậy:

- Nội dung của bài này áp dụng cho quy trình JDK 25.
- Khi chạy đúng JDK 25 với AOT cache, dùng collector được hỗ trợ và kiểm chứng trên bản JDK/vendor mục tiêu.
- Nếu nâng lên JDK 26 hoặc mới hơn, kiểm tra tài liệu của release đó; không áp dụng máy móc giới hạn ZGC của JDK 25.

## 12. Tài nguyên cần cho training và assembly

Với `-XX:AOTCacheOutput`, JVM tự khởi chạy tiến trình thứ hai để assembly khi training kết thúc. Tiến trình assembly sử dụng heap riêng; trong môi trường giới hạn tài nguyên, nhu cầu bộ nhớ trong khoảng thời gian hai tiến trình chồng lấp có thể xấp xỉ gấp đôi heap đã cấu hình cho training.

Ví dụ nếu training JVM dùng `-Xmx2g`, hãy dự trù thêm RAM cho JVM assembly và overhead của hệ điều hành/container. Đừng giả định toàn bộ RAM container chỉ cần bằng `-Xmx` của một JVM.

~~~bash
java -Xms1g -Xmx2g \
     -XX:AOTCacheOutput=app.aot \
     -cp app.jar com.example.App training
~~~

Nếu không đủ tài nguyên để hai JVM cùng chạy, có thể tách `record` và `create`:

- Training chạy trên máy có workload và môi trường gần production.
- Assembly chạy trong job riêng có nhiều RAM/CPU hơn nhưng vẫn phải phù hợp JDK release, OS và CPU architecture của đích triển khai.
- Lưu `app.aotconfig` làm artifact trung gian có version.
- Không chuyển file cache qua kiến trúc hoặc hệ điều hành khác.

JDK 25 cho phép truyền JVM options bổ sung cho tiến trình assembly qua biến môi trường `JDK_AOT_VM_OPTIONS`. Đây là lựa chọn nâng cao; chỉ cấu hình khi cần điều chỉnh tiến trình tạo cache và đã hiểu rõ các tùy chọn tương thích.

## 13. Kiểm tra cache có được nạp thật hay không

Ứng dụng khởi động thành công không có nghĩa cache đã được dùng. Cần xem log AOT và class loading.

### Bật log AOT

~~~bash
java -Xlog:aot \
     -XX:AOTCache=app.aot \
     -cp app.jar com.example.App
~~~

Tìm thông báo liên quan tới cache load, mismatch hoặc điều kiện khiến cache bị bỏ qua.

### Bật class loading log

~~~bash
java -Xlog:class+load=info:file=class-load.log \
     -XX:AOTCache=app.aot \
     -cp app.jar com.example.App
~~~

Log giúp quan sát nguồn tải class; class lấy từ cache có thể hiển thị nguồn dạng `shared objects file`. Không nên chỉ kiểm tra vài class rồi kết luận mọi class đều được cache.

### Chế độ kiểm tra fail-fast

~~~bash
java -XX:AOTCache=app.aot \
     -XX:AOTMode=on \
     -Xlog:aot \
     -cp app.jar com.example.App
~~~

`AOTMode=on` yêu cầu cache phải được nạp thành công; nếu không, JVM báo lỗi. Dùng trong CI/staging để kiểm tra tính tương thích. Sau khi xác minh, production thường nên để `auto` để ứng dụng vẫn có thể chạy nếu cache không được nạp.

## 14. Đo hiệu quả: startup và warm-up là hai chỉ số khác nhau

AOT cache hướng tới cả startup và warm-up, nhưng hai mục tiêu này không đồng nhất:

- **Startup:** thời gian từ khi JVM bắt đầu đến khi ứng dụng sẵn sàng phục vụ công việc đầu tiên.
- **Warm-up:** thời gian để throughput/latency đạt trạng thái ổn định sau khi ứng dụng đã chạy.

JEP 515 bổ sung method profiles vào cache, nên workload training có ảnh hưởng tới hiệu quả warm-up. Nếu chỉ training startup, không thể kỳ vọng cache chứa profile tốt cho những method nghiệp vụ chưa từng được gọi.

### Bộ chỉ số nên đo

| Chỉ số | Cách đo |
| --- | --- |
| Startup p50/p95 | Nhiều lần cold start trong cùng điều kiện |
| Time-to-ready | Từ khi JVM start tới readiness thực tế |
| Warm-up latency | p50/p95/p99 theo từng giai đoạn sau start |
| Throughput | Request/second hoặc records/second theo workload |
| CPU | CPU time/utilization trong startup và warm-up |
| Memory | RSS, heap, container memory |
| Cache artifact | Kích thước file `.aot`, thời gian tạo và phân phối |
| Reliability | Error rate, restart, cache load failures |

### So sánh có kiểm soát

1. Chạy cùng artifact **không có cache** làm baseline.
2. Tạo cache bằng workload training cố định.
3. Chạy lại cùng artifact **có cache**.
4. Lặp lại nhiều lần, luân phiên thứ tự thử để giảm ảnh hưởng nhiệt độ máy hoặc background load.
5. Dùng cùng JDK, GC, heap, CPU limit, OS và classpath.
6. So sánh startup và warm-up riêng biệt.
7. Đánh giá cả kích thước cache, thời gian training/assembly và chi phí CI.

Không lấy số benchmark của một chương trình demo làm cam kết cho dịch vụ có database, network, TLS hoặc framework initialization phức tạp. Kết quả phụ thuộc workload, môi trường và độ tương đồng giữa training với production.

## 15. Lỗi thường gặp và hướng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không có file `.aot` sau training | Process chưa kết thúc/recording chưa hoàn tất; quyền ghi file | Kiểm tra JVM exit, log và đường dẫn |
| Cache không load | Khác JDK release, OS, CPU, classpath hoặc JVM options | Tạo lại cache trong môi trường đích |
| Cache load nhưng không cải thiện | Workload training không đại diện hoặc bottleneck nằm ở I/O | Đo startup/warm-up và profiling riêng |
| Chỉ startup cải thiện | Training không thực thi business methods | Thêm workload production-like để thu method profiles |
| Cache quá lớn | Training tải nhiều class không cần thiết | Giảm test framework/unused paths trong training |
| Assembly bị OOM | Hai JVM cùng cần heap và RAM | Tăng tài nguyên hoặc tách record/create |
| Spring Boot cache không có tác dụng | Chạy uber JAR thay vì extracted layout | Dùng tools jarmode extract và đúng layout |
| `AOTMode=on` báo lỗi | Cache không tương thích hoặc không tồn tại | Kiểm tra `-Xlog:aot`, classpath và JVM flags |
| Dùng JDK 25 với ZGC | AOT object cache của JDK 25 chưa hỗ trợ ZGC | Dùng collector được hỗ trợ hoặc đánh giá JDK 26+ |
| Cache sau deploy cũ | Artifact/dependency mới nhưng cache chưa tạo lại | Tạo cache cùng build artifact mới |

### Quy trình khoanh vùng

~~~mermaid
flowchart TD
    A["Tạo cache bằng JDK 25"] --> B{"File .aot được tạo?"}
    B -->|Không| C["Kiểm tra training exit, quyền ghi, assembly và RAM"]
    B -->|Có| D["Chạy với -XX:AOTMode=on -Xlog:aot"]
    D --> E{"Cache được nạp?"}
    E -->|Không| F["So sánh JDK, OS/CPU, classpath, JAR timestamps và JVM options"]
    E -->|Có| G["Đo startup và warm-up"]
    G --> H{"Đạt mục tiêu?"}
    H -->|Không| I["Cải thiện workload training hoặc bỏ cache nếu không có lợi"]
    H -->|Có| J["Đóng gói cache cùng artifact và rollout"]
~~~

## 16. Tự động hóa trong CI/CD

Cache phải được tạo từ đúng artifact sẽ triển khai. Một pipeline có thể chia thành:

1. **Build:** biên dịch, test, đóng gói ứng dụng.
2. **Extract:** tạo layout phù hợp nếu ứng dụng dùng Spring Boot executable JAR.
3. **Training:** chạy workload đại diện bằng đúng JDK và môi trường tương thích.
4. **Assembly:** tạo file `.aot`.
5. **Verify:** khởi động ứng dụng với `-XX:AOTMode=on`, kiểm tra log và smoke test.
6. **Package:** lưu cache cùng artifact metadata.
7. **Deploy:** truyền `-XX:AOTCache=<path>` cho production process.
8. **Observe:** đo startup/warm-up và tỷ lệ cache load thành công.

### Metadata nên lưu cùng cache

~~~yaml
applicationArtifact: "service-1.4.2.jar"
applicationSha256: "<artifact-digest>"
jdkVendor: "<vendor>"
jdkVersion: "25"
os: "<target-os>"
architecture: "<target-cpu>"
collector: "<supported-gc>"
trainingProfile: "smoke-plus-business-workflow"
cacheFile: "service.aot"
createdAt: "<timestamp>"
~~~

Đây là metadata minh họa cho pipeline, không phải định dạng cấu hình chuẩn của JVM. Giá trị digest, JDK build và target platform cần được pipeline điền thực tế.

Không đưa cache vào một registry chung mà không gắn với artifact/version/platform. Khi code, dependency, JDK release hoặc OS/CPU thay đổi, tạo lại cache và xác minh trước khi deploy.

## 17. An toàn khi training ứng dụng có side effects

Training chạy ứng dụng thật. Nếu ứng dụng gửi email, gọi payment, ghi database hoặc tiêu thụ message, các hành động này có thể xảy ra trong môi trường training.

Trước khi chạy:

- Dùng database sandbox hoặc dữ liệu test có thể reset.
- Mock/stub payment, email, SMS và các external services có side effects.
- Không dùng dữ liệu cá nhân hoặc bí mật production nếu không có quy trình phê duyệt.
- Đảm bảo message queue không tiêu thụ nhầm message production.
- Không để training tạo hóa đơn, thanh toán, notification hoặc job thật.
- Ghi lại cấu hình và workload để có thể tái lập.
- Giới hạn quyền ghi file, network và secret access của training job.

Nếu cần dùng production workload để thu profile, phải thiết kế quy trình riêng có kiểm soát, quan sát và bảo vệ dữ liệu. Training không phải lý do để phát lại request tùy tiện lên hệ thống production.

## 18. Bài thực hành: tạo cache cho ứng dụng Java 25

### Phần A — Ứng dụng đơn giản

1. Cài JDK 25 và xác nhận `java -version`.
2. Build một JAR chạy được với main class.
3. Chạy baseline không cache và ghi startup/warm-up.
4. Tạo cache:

~~~bash
java -XX:AOTCacheOutput=demo.aot \
     -cp demo.jar com.example.App training
~~~

5. Kiểm tra file `demo.aot` đã được tạo.
6. Chạy lại:

~~~bash
java -XX:AOTCache=demo.aot \
     -cp demo.jar com.example.App production
~~~

7. Bật `-Xlog:aot` để xác nhận cache load.
8. So sánh nhiều lần chạy, ghi startup p50/p95 và warm-up throughput.

### Phần B — Training có method profile

1. Chọn ít nhất hai đường nghiệp vụ thường xuyên được sử dụng.
2. Thiết kế workload test gọi các đường đó với input đại diện.
3. Chạy ứng dụng với `-XX:AOTCacheOutput=demo.aot`.
4. Giữ ứng dụng hoạt động trong khi workload chạy; sau đó kết thúc training.
5. Tạo cache và chạy lại cùng workload.
6. So sánh warm-up của các method được training với những nhánh không được gọi.
7. Thay đổi workload training và quan sát ảnh hưởng tới cache.

### Phần C — Spring Boot

1. Build executable JAR.
2. Dùng `-Djarmode=tools` extract application.
3. Chạy startup-only training với `spring.context.exit=onRefresh` để thấy giới hạn của cách này.
4. Chạy một lần khác với workflow gần production: khởi động server, gửi request nghiệp vụ, sau đó kết thúc training có kiểm soát.
5. Tạo cache và khởi động lại bằng `-XX:AOTCache`.
6. Kiểm tra log class loading, startup time và warm-up latency.

### Câu hỏi tự đánh giá

- JEP 514 thay đổi điều gì trong cách tạo AOT cache của JDK 25?
- JEP 515 bổ sung dữ liệu gì vào cache và cải thiện phần nào?
- Vì sao một lệnh `AOTCacheOutput` vẫn có thể khởi chạy JVM thứ hai?
- Khi nào nên tách `record` và `create`?
- Vì sao training chỉ dùng `spring.context.exit=onRefresh` chưa đủ cho method profiling?
- Cache gắn với những đặc điểm nào của ứng dụng và môi trường?
- Tại sao không thể tạo cache một lần rồi dùng cho mọi OS/CPU?
- Khi nào dùng `AOTMode=on` để xác minh và khi nào dùng `auto`?
- Vì sao JDK 25 cần lưu ý giới hạn ZGC?
- Làm thế nào để training không gửi email hoặc thanh toán thật?
- Nếu startup không đổi nhưng warm-up tốt hơn, điều đó có thể cho biết gì về method profiles?

## 19. Checklist trước khi phát hành AOT cache

- [ ] Training dùng JDK 25 và cùng target OS/CPU với production.
- [ ] Cache được tạo từ đúng artifact và classpath của bản phát hành.
- [ ] Classpath/JAR order và timestamps được giữ nhất quán.
- [ ] Workload training đại diện cho startup và các luồng nghiệp vụ cần tối ưu.
- [ ] Nếu muốn hưởng lợi JEP 515, training đã thực thi các method nóng.
- [ ] Training không gây side effects production hoặc lộ dữ liệu nhạy cảm.
- [ ] File `.aot` được tạo đầy đủ và có quyền đọc ở runtime.
- [ ] Assembly đủ RAM; nếu cần đã tách training và create.
- [ ] Cache được xác minh bằng `-XX:AOTMode=on` và log AOT.
- [ ] Startup/warm-up được đo với baseline cùng điều kiện.
- [ ] Đã kiểm tra GC; không giả định JDK 25 hỗ trợ ZGC cho AOT cache.
- [ ] Cache được version hóa cùng application artifact, JDK và platform.
- [ ] Có quy trình tái tạo cache khi build/dependency/JDK/platform thay đổi.
- [ ] Production có thể chạy tiếp nếu cache không được nạp theo chế độ `auto`.
- [ ] Có phương án rollback về khởi chạy không dùng cache.

**Tiêu chí hoàn thành:** người học có thể tạo AOT cache trên JDK 25 bằng `-XX:AOTCacheOutput`, giải thích quá trình training/assembly tự động, chọn workload đại diện để thu class data và method profiles, xác minh cache được nạp, đo startup/warm-up và đóng gói cache đúng với artifact/platform. Cache chỉ được phát hành khi có bằng chứng tương thích và hiệu quả; ứng dụng vẫn phải chạy đúng khi không dùng cache.

## 20. Tài liệu chính thức

- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): nền tảng AOT cache được giới thiệu ở JDK 24.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): cơ chế `-XX:AOTCacheOutput` giúp training và assembly trong một invocation.
- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): method profiles được thu thập trong training và lưu vào AOT cache của Java 25.
- [The java Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `AOTCache`, `AOTCacheOutput`, `AOTConfiguration`, `AOTMode` và hành vi cache load.
- [The jcmd Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): lệnh `AOT.end_recording`.
- [HotSpotAOTCacheMXBean — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/jdk/management/HotSpotAOTCacheMXBean.html): vòng đời AOT recording.
- [Spring Boot — AOT Cache](https://docs.spring.io/spring-boot/reference/packaging/aot-cache.html): extraction và sử dụng AOT cache với executable JAR.
- [Spring Framework — JVM AOT Cache](https://docs.spring.io/spring-framework/reference/integration/aot-cache.html): training, production-like workflow, classpath và class loading.
- [Inside Java — Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): hướng dẫn training, assembly, điều kiện tương thích, giới hạn tài nguyên và kiểm tra cache.

Khi nâng JDK, cần kiểm tra tài liệu của đúng release đang chạy. Ví dụ giới hạn ZGC nêu trong bài áp dụng cho AOT cache của JDK 25; JDK 26 có JEP 516 mở rộng AOT object caching cho các GC khác. Không chuyển một giới hạn của Java 25 thành khẳng định cho mọi JDK mới hơn.
