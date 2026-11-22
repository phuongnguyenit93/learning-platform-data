# Kiểm tra contention và concurrency stress với jcstress (công cụ ngoài JDK)

## 1. Vì sao cần jcstress?

Code Java nhiều thread có thể chạy đúng hàng nghìn lần rồi sai một lần vì lịch chạy hiếm gặp, mất cập nhật, visibility, race hoặc vi phạm thứ tự của Java Memory Model (JMM). Test đơn luồng, JUnit thông thường hoặc thử gọi Thread.sleep() thường không chủ động thăm dò đủ nhiều tương tác thời gian giữa các thread.

**Java Concurrency Stress (jcstress)** là bộ công cụ thực nghiệm thuộc dự án OpenJDK Code Tools. Nó tạo nhiều lần chạy song song của các **actor**, thu thập các trạng thái kết quả, đối chiếu chúng với những **outcome đã phân loại** rồi báo cáo những trường hợp chấp nhận được, đáng chú ý hoặc bị cấm. jcstress đặc biệt hữu ích để nghiên cứu hành vi JVM/JMM và kiểm tra các cấu trúc dữ liệu/thuật toán concurrency ở quy mô nhỏ.

**Điểm quan trọng:** jcstress là **công cụ ngoài JDK**. Muốn sử dụng cần tải dependency/build harness tương thích (ví dụ qua Maven archetype), chứ Java 17/21 không cung cấp lệnh jcstress hoặc các annotation đó sẵn.

Phạm vi bài này là concurrency Java nói chung, dùng JDK và jcstress. Các thành phần phụ thuộc framework nằm ngoài phạm vi.

### Sau bài này bạn có thể

1. Phân biệt **race condition**, **data race**, **contention**, **stress test**, **JCStress outcome** và **benchmark hiệu năng**.
2. Tự tạo dự án jcstress độc lập với Maven, viết một test có hai actor và arbiter, biên dịch và chạy.
3. Giải thích vì sao phép tăng x++ có thể mất cập nhật và cách thay bằng AtomicInteger.
4. Dùng test “message passing” để so sánh trường thường với volatile theo happens-before của JMM.
5. Biết cách kiểm tra một biểu hiện contention mà không nhầm số lần xuất hiện outcome với latency/throughput.
6. Diễn giải báo cáo ACCEPTABLE, ACCEPTABLE_INTERESTING, FORBIDDEN và giới hạn kiểm chứng xác suất.

## 2. Những vấn đề jcstress tìm kiếm

### 2.1. Race condition và data race

- **Race condition**: kết quả phụ thuộc vào thứ tự hoặc thời điểm thực thi của các tác vụ đồng thời. Không phải race condition nào cũng là lỗi; có những thứ tự được thiết kế hợp lệ.
- **Data race** theo cách mô tả JMM: các hành động đọc/ghi xung đột trên cùng biến mà không được sắp theo happens-before; không có đồng bộ thích hợp để thiết lập quan hệ đó. Một race có thể dẫn đến các kết quả khó dự đoán nhưng Java vẫn có các quy tắc JMM; không được suy rằng “mọi thứ đều có thể xảy ra”.
- **Atomicity**: một hành động hoặc chuỗi hành động được quan sát như một đơn vị không thể bị xen giữa theo contract. Thao tác x++ gồm đọc, cộng và ghi; biến int có đọc/ghi đơn lẻ nguyên tử ở mức tương ứng nhưng x++ không nguyên tử.
- **Visibility**: một thread có thấy dữ liệu mà thread khác ghi không. “Code chạy theo thứ tự dòng” ở mỗi thread không đủ đảm bảo thread khác quan sát các write theo cùng thứ tự nếu thiếu happens-before.
- **Ordering**: compiler, JIT và CPU có thể thực hiện tối ưu/đổi thứ tự các hành động trong giới hạn JMM. Cần chứng minh theo quan hệ happens-before thay vì dựa vào cảm giác “dòng này trước dòng kia”.

**Ví dụ:** hai thread cùng tăng biến int từ 0 lên 1 lần. Nếu cả hai đọc giá trị 0 rồi ghi 1, kết quả cuối bằng 1 thay vì 2. Đó là lost update.

### 2.2. Contention không đồng nghĩa với data race

**Contention** là nhiều thread cùng cạnh tranh một tài nguyên: monitor/lock, semaphore, atomic variable, cùng cache line, queue, CPU, hoặc memory bandwidth. Có contention ngay cả khi code đúng và không có data race.

- synchronized đúng về mutual exclusion nhưng nhiều thread có thể chờ một lock, dẫn tới tail latency tăng.
- AtomicInteger tránh lost update nhưng cập nhật dồn vào cùng một biến vẫn có thể tạo cache coherence contention.
- Giảm contention bằng sharding, local accumulation hoặc LongAdder có thể nâng throughput, nhưng không tự chứng minh mọi contract nghiệp vụ.

**jcstress đánh giá tính đúng đắn quan sát được của kết quả concurrent.** Công cụ này có thể gây contention trong quá trình các actor chạy để thăm dò interleavings, nhưng **không phải** trình đo latency/throughput hoặc bộ phân tích thời gian chờ monitor. Muốn định lượng contention, dùng JMH, JFR, ThreadMXBean hoặc profiler/counters hệ điều hành trong một thí nghiệm riêng.

### 2.3. Vì sao vòng for chạy triệu lần chưa đủ?

Một vòng lặp tự viết như sau thường gây hiểu nhầm:

~~~java
for (int i = 0; i < 1_000_000; i++) {
    new Thread(() -> shared++).start();
}
~~~

Nó không chờ toàn bộ threads, tạo chi phí hàng triệu thread và không tự phân loại kết quả hợp lệ. Ngay cả sửa bằng join(), chương trình vẫn chỉ khảo sát một cách rất kém kiểm soát lịch chạy và không tránh những tối ưu JIT có thể làm che hành vi.

jcstress tổ chức **rendezvous, nhiều state instances, nhiều lần thử, nhiều cấu hình JVM/CPU tùy chế độ**, thu thập frequency và đặt outcome vào contract rõ ràng. Harness không “điều khiển được mọi lịch chạy” và không chứng minh kết quả hiếm sẽ xuất hiện trong khoảng thời gian hữu hạn.

## 3. Mô hình thực thi của jcstress

Một phép thử cơ bản có:

- **@JCStressTest** đặt trên class test để harness nhận diện.
- **@State** mô tả đối tượng trạng thái mà các actor cùng đọc/ghi. Trong ví dụ đơn giản có thể đánh dấu class test bằng cả @JCStressTest lẫn @State.
- **@Actor** đặt trên các method chạy cạnh tranh. Trình tự hoàn thành giữa các actor **không được giả định**.
- **@Arbiter** tùy chọn, đọc trạng thái sau khi tất cả actor hoàn tất đối với state đó; thích hợp cho kiểm tra kết quả cuối cùng mà không tạo thêm race với actor.
- **@Outcome(id, expect, desc)** mô tả kết quả kỳ vọng và cách xếp loại, dựa trên chuỗi biểu diễn của result.
- **I_Result / II_Result / ...** là những result holder có sẵn; chữ I biểu thị int, II_Result có hai trường r1/r2 kiểu int. Result object được harness quản lý, không tự tạo bằng new trong actor.

Dòng đời khái niệm:

~~~text
jcstress harness
  -> tạo đối tượng @State mới cho một lượt thử
  -> cho actor1 và actor2 cùng chạy với lịch không xác định
  -> (nếu có) gọi @Arbiter khi cả hai actor đã kết thúc
  -> lấy result, chuyển thành outcome ID
  -> tăng frequency của outcome tương ứng
  -> lặp lại với nhiều state/lượt/đợt
  -> phân loại kết quả và sinh báo cáo
~~~

Trạng thái instance/constructor ban đầu được tạo cho lượt thử trước khi các actor được điều phối; actor không được tự chia sẻ biến static giữa nhiều lượt trừ khi bạn thật sự có ý định thử global state. Các phép thử tốt giữ state nhỏ, độc lập và tối thiểu hóa tác động phụ như I/O.

### 3.1. Ba mức outcome quan trọng

| Expect | Nghĩa | Hành động khi kết quả xuất hiện |
|---|---|---|
| ACCEPTABLE | Kết quả **được phép** theo contract | Không coi là lỗi dù xuất hiện với tần suất khác nhau |
| ACCEPTABLE_INTERESTING | Kết quả hợp lệ nhưng đáng quan sát/điều tra | Báo cáo đánh dấu nổi bật, giúp minh họa hiện tượng hiếm |
| FORBIDDEN | Kết quả **không được phép** theo contract mà test đã khai báo | Coi là tín hiệu bất thường; kiểm tra test, kỳ vọng, harness, JVM, hardware và chạy lại |

**ACCEPTABLE không có nghĩa bắt buộc phải xuất hiện.** Một outcome hợp lệ có thể không quan sát được. **FORBIDDEN** chỉ đáng tin khi oracle đúng: nếu xếp nhầm outcome hợp lệ vào FORBIDDEN thì báo cáo sẽ là false positive.

Outcome ID cần khớp định dạng thực tế của Result class. Với I_Result, ID thông thường là "1" hoặc "2"; với II_Result, dạng "0, 1". Không suy diễn ID từ số lần actor chạy hoặc thứ tự thread.

## 4. Cài đặt jcstress: dự án Maven chuyên biệt

OpenJDK khuyến nghị tạo **module/dự án jcstress riêng** vì harness cần annotation processing, đóng gói test list và một executable JAR. Chỉ thêm jcstress-core vào một module Java bình thường chưa chắc tạo được JAR chạy đúng.

Yêu cầu thực tế:

- Java Development Kit (nên dùng **JDK 17+** cho ví dụ), lệnh java và javac hoạt động.
- Maven trên máy, truy cập Maven Central để tải artifacts nếu chưa được cache.
- Hệ điều hành cho phép khởi chạy nhiều JVM/threads và đủ CPU/memory để chạy stress.

Kiểm tra môi trường:

~~~bash
java -version
javac -version
mvn -version
~~~

Tạo dự án với Maven archetype được hướng dẫn trong README chính thức của OpenJDK (lệnh một dòng chạy trong shell thông thường):

~~~bash
mvn archetype:generate -DinteractiveMode=false -DarchetypeGroupId=org.openjdk.jcstress -DarchetypeArtifactId=jcstress-java-test-archetype -DgroupId=org.sample -DartifactId=jcstress-lab -Dversion=1.0
~~~

Ở đây -Dversion=1.0 là phiên bản dự án tạo ra; Maven resolve phiên bản archetype theo repository. Nếu hệ thống yêu cầu chọn phiên bản, chọn bản jcstress archetype phát hành tương thích và ghi phiên bản vào tài liệu nhóm để build có thể tái lập.

~~~bash
cd jcstress-lab
mvn clean verify
java -jar target/jcstress.jar -h
~~~

**mvn clean verify** biên dịch và đóng gói, còn **java -jar target/jcstress.jar** mới chạy stress test. Việc xây dựng artifact không đồng nghĩa đã chạy toàn bộ stress workload.

Cấu trúc quan trọng, tên cụ thể có thể thay đổi theo archetype:

~~~text
jcstress-lab/
  pom.xml
  src/main/java/org/sample/
    LostUpdateTest.java
    AtomicIncrementTest.java
    PlainPublicationTest.java
    VolatilePublicationTest.java
  target/jcstress.jar      (sau khi mvn clean verify)
~~~

Nếu archetype đã sinh test mẫu, có thể giữ lại và thêm các class bên dưới. Đừng ghi đè các file mẫu mà chưa kiểm tra. **Mỗi public class Java nằm trong file trùng tên**, package được đặt đúng đường dẫn.

### 4.1. Chạy một test và chọn cường độ

~~~bash
mvn clean verify
java -jar target/jcstress.jar -t '.*LostUpdateTest' -m quick
~~~

Trên Windows PowerShell có thể dùng dấu nháy đơn tương tự. Tham số -t lọc test theo tên; đặt pattern khớp class muốn chạy để tránh chạy toàn bộ thư viện. Tham số -m chọn preset cường độ/thời lượng; quick phù hợp feedback nhanh nhưng **ít sample hơn**, dễ bỏ lỡ một outcome hiếm.

Tham khảo lựa chọn thực tế của bản đang dùng bằng:

~~~bash
java -jar target/jcstress.jar -h
~~~

Không tự đoán số fork, threads, stress time hoặc Java flags từ một bản khác; options có thể đổi theo phiên bản. Khi chạy CI nhanh có thể dùng -m quick; khi đang điều tra race hiếm cần tăng thời gian/số lượt, chạy trên thêm CPU/JDK và kiểm soát tài nguyên.

## 5. Ví dụ 1: tái hiện lost update bằng hai actor

File **src/main/java/org/sample/LostUpdateTest.java**:

~~~java
package org.sample;

import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Arbiter;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.I_Result;

@JCStressTest
@State
@Outcome(id = "1", expect = Expect.ACCEPTABLE_INTERESTING,
        desc = "Lost update: both actors read 0 then write 1.")
@Outcome(id = "2", expect = Expect.ACCEPTABLE,
        desc = "Both increments contributed to the final value.")
public class LostUpdateTest {
    private int counter;

    @Actor
    public void actor1() {
        counter++;
    }

    @Actor
    public void actor2() {
        counter++;
    }

    @Arbiter
    public void arbiter(I_Result result) {
        result.r1 = counter;
    }
}
~~~

**Vì sao kết quả là 1 hoặc 2?** Mỗi actor thực hiện một phép tăng không nguyên tử trên cùng biến counter mặc định 0. Nếu cả hai cùng đọc 0 trước khi ghi, mỗi actor đều ghi 1, phép tăng bị mất. Nếu một phép tăng hoàn tất trước khi phép khác đọc thì kết quả 2.

Lịch tương tác minh họa:

~~~text
counter ban đầu = 0

actor1                 actor2
  read 0
                         read 0
  compute 1
                         compute 1
  write 1
                         write 1

@Arbiter đọc counter = 1
~~~

Không khẳng định harness **chắc chắn** quan sát được 1 trong mọi lần chạy. Nếu chỉ thấy 2, test vẫn chưa chứng minh phép ++ nguyên tử. Outcome 1 **hợp lệ theo hành vi chương trình đang có data race** nhưng là hiện tượng đáng cảnh báo nếu yêu cầu nghiệp vụ là “không mất cập nhật”.

### 5.1. Kiểm tra cách sửa bằng AtomicInteger

File **src/main/java/org/sample/AtomicIncrementTest.java**:

~~~java
package org.sample;

import java.util.concurrent.atomic.AtomicInteger;
import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Arbiter;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.I_Result;

@JCStressTest
@State
@Outcome(id = "2", expect = Expect.ACCEPTABLE,
        desc = "Both atomic increments are counted.")
@Outcome(expect = Expect.FORBIDDEN,
        desc = "No other final result is allowed.")
public class AtomicIncrementTest {
    private final AtomicInteger counter = new AtomicInteger();

    @Actor
    public void actor1() {
        counter.incrementAndGet();
    }

    @Actor
    public void actor2() {
        counter.incrementAndGet();
    }

    @Arbiter
    public void arbiter(I_Result result) {
        result.r1 = counter.get();
    }
}
~~~

Ở đây hai lần **incrementAndGet()** trên cùng AtomicInteger có hiệu ứng cập nhật nguyên tử; sau khi hai actor đã xong, arbiter phải thấy 2. Outcome thứ hai không có id cụ thể là quy tắc mặc định cho mọi kết quả không được liệt kê: **FORBIDDEN**.

Giải pháp khác là dùng chung synchronized/Lock bao quanh thao tác tăng. Với đúng hai lượt tăng, AtomicInteger là cách dễ thấy tính atomic và đơn giản trong bài học. **Không dùng volatile int counter rồi counter++** để “sửa”: volatile giúp visibility/order theo JMM cho các truy cập volatile nhưng không biến toán tử read-modify-write ++ thành một thao tác nguyên tử.

### 5.2. Chạy và diễn giải

~~~bash
mvn clean verify
java -jar target/jcstress.jar -t '.*LostUpdateTest' -m quick
java -jar target/jcstress.jar -t '.*AtomicIncrementTest' -m quick
~~~

Output tóm tắt của harness thường gồm outcome, số lần quan sát/frequency, expectation và mô tả. **Không có stdout cố định**: tần suất kết quả phụ thuộc CPU/JIT/JVM/scheduling, thời lượng và mode. Hãy mở báo cáo HTML do jcstress sinh (thường dưới thư mục results/ trong working directory, đường dẫn cụ thể được in khi chạy).

Kết quả mong đợi về **tính đúng đắn của contract**:

| Test | Outcome | Phân loại | Ý nghĩa |
|---|---|---|---|
| LostUpdateTest | 1 | ACCEPTABLE_INTERESTING | Có thể mất một update |
| LostUpdateTest | 2 | ACCEPTABLE | Không mất update trong lượt đó |
| AtomicIncrementTest | 2 | ACCEPTABLE | Đúng contract khi hai actor đều hoàn tất |
| AtomicIncrementTest | khác 2 | FORBIDDEN | Vi phạm contract hoặc có lỗi trong test/môi trường |

Không biến số lượng outcome 1 thành “x% người dùng thực gặp lỗi”: stress harness cố tăng cơ hội phát hiện các interleaving, không mô phỏng phân phối workload sản xuất.

## 6. Ví dụ 2: kiểm tra visibility và message passing

Ví dụ sau xem xét publication qua hai biến:

- Writer gán data = 42 rồi gán ready = true.
- Reader đọc ready; nếu true thì đọc data, nếu false thì ghi -1 vào result.
- Dấu hiệu đáng chú ý là reader thấy **ready = true nhưng data = 0**, chứng tỏ không có đảm bảo hiển thị write data trước cho thread khác.

### 6.1. Phiên bản thiếu đồng bộ: plain fields

File **src/main/java/org/sample/PlainPublicationTest.java**:

~~~java
package org.sample;

import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.I_Result;

@JCStressTest
@State
@Outcome(id = "-1", expect = Expect.ACCEPTABLE,
        desc = "Reader checked ready before seeing publication.")
@Outcome(id = "42", expect = Expect.ACCEPTABLE,
        desc = "Reader saw data after publication.")
@Outcome(id = "0", expect = Expect.ACCEPTABLE_INTERESTING,
        desc = "Flag looked ready, payload was not visible.")
public class PlainPublicationTest {
    int data;
    boolean ready;

    @Actor
    public void writer() {
        data = 42;
        ready = true;
    }

    @Actor
    public void reader(I_Result result) {
        result.r1 = ready ? data : -1;
    }
}
~~~

Vì data và ready là các trường thông thường, chương trình **không thiết lập happens-before** từ writer tới reader. Outcome 0 được JMM cho phép về visibility/order dù trong source writer viết data trước ready. **Khả năng được phép** không có nghĩa mọi máy đều quan sát được outcome 0. Nếu không thấy 0 sau các lượt chạy, vẫn chưa sửa được data race.

Nếu reader thấy ready false (bất kể writer đang ở đâu), kết quả -1 là được phép. Nếu thấy flag và payload đúng, kết quả 42 cũng được phép.

### 6.2. Phiên bản dùng volatile: đảm bảo publication

File **src/main/java/org/sample/VolatilePublicationTest.java**:

~~~java
package org.sample;

import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.I_Result;

@JCStressTest
@State
@Outcome(id = "-1", expect = Expect.ACCEPTABLE,
        desc = "Reader runs before it observes the ready flag.")
@Outcome(id = "42", expect = Expect.ACCEPTABLE,
        desc = "Volatile flag publishes preceding data write.")
@Outcome(expect = Expect.FORBIDDEN,
        desc = "Other outcomes violate the expected publication contract.")
public class VolatilePublicationTest {
    int data;
    volatile boolean ready;

    @Actor
    public void writer() {
        data = 42;
        ready = true;
    }

    @Actor
    public void reader(I_Result result) {
        result.r1 = ready ? data : -1;
    }
}
~~~

**Vì sao khi ready true, data phải bằng 42?** Write vào volatile ready có quan hệ **synchronizes-with** với read volatile ready thấy publication đó. Theo tính bắc cầu happens-before, write thường data = 42 nằm trước volatile write cũng phải được quan sát đúng bởi reader khi nó đã thấy ready true. Trong case này reader đọc ready một lần rồi mới đọc data; không có actor thứ ba đổi data.

Nếu reader chưa nhìn thấy ready true, kết quả -1 vẫn hợp lệ. **Không cần đặt volatile cho data** trong ví dụ message passing này, miễn là toàn bộ giao thức publish/read tuân thủ cùng điều kiện và không có write khác sau publication gây race mới.

### 6.3. Chạy thử

~~~bash
mvn clean verify
java -jar target/jcstress.jar -t '.*PlainPublicationTest' -m quick
java -jar target/jcstress.jar -t '.*VolatilePublicationTest' -m quick
~~~

| Outcome | PlainPublicationTest | VolatilePublicationTest |
|---|---|---|
| -1 | ACCEPTABLE | ACCEPTABLE |
| 42 | ACCEPTABLE | ACCEPTABLE |
| 0 | ACCEPTABLE_INTERESTING | FORBIDDEN |
| kết quả bất thường khác | Cần rà soát oracle | FORBIDDEN |

Bảng nêu **phân loại logic**, không phải tần suất đo. Nếu một outcome FORBIDDEN xuất hiện, cần tái lập và kiểm tra cả cách viết test/annotation/result trước khi quy lỗi cho JVM hoặc hardware.

## 7. Thiết kế stress test cho một vấn đề contention thực tế

### 7.1. Nên bắt đầu từ invariant, không phải số thread

Ví dụ bài toán: một số dư bị cộng và trừ đồng thời. Hãy định nghĩa rõ invariant trước:

- Tất cả operation hoàn tất trước khi arbiter đọc thì tổng cuối phải bằng giá trị kỳ vọng.
- Nếu contract cho phép thử/cập nhật thất bại, cần phân biệt thành công và từ chối.
- Nếu cần linearizability, kiểm tra từng operation/return value so với một thứ tự tuần tự hợp lệ, chứ chỉ kiểm tra tổng cuối **chưa đủ**.
- Nếu đối tượng là collection, cần xét cả uniqueness, visibility, ordering, null/missing entries hoặc trạng thái không nhất quán, tùy API contract.
- Nếu concurrency primitive có thể timeout/cancel, cần đưa các đường đó vào state/outcome.

Sau đó rút gọn còn **ít actor, ít trường, ít logic**. Bài học quan trọng nhất là có một **oracle đúng**: mô tả chính xác outcome nào được JMM/API cho phép, outcome nào không. Nếu oracle quá mạnh, bạn sẽ báo lỗi giả; nếu quá yếu, test sẽ bỏ qua bug.

### 7.2. Khai thác contention có kiểm soát

Ví dụ một resource được bảo vệ bằng synchronized:

~~~java
private final Object lock = new Object();
private int balance;

void deposit() {
    synchronized (lock) {
        balance++;
    }
}

void withdraw() {
    synchronized (lock) {
        balance--;
    }
}
~~~

Đây là đoạn code minh họa **chưa phải một class jcstress độc lập**. Nếu test tạo hai actor gọi deposit()/withdraw(), arbiter đọc balance sau khi hai actor kết thúc thì final phải là 0 từ state khởi tạo 0. Nhưng để kiểm tra contention **về hiệu năng**, phải đo lock hold/wait, throughput và latency ở workload khác; jcstress chỉ có thể xác nhận atomicity/invariant của phiên bản rút gọn.

Tăng actor count hoặc vòng lặp trong actor không luôn làm test hay hơn. Vòng lặp dài có thể khiến một actor chiếm quá lâu, giảm độ đa dạng interleavings và phóng đại tác động của test harness. Nên bắt đầu từ litmus nhỏ, chỉ thêm actors/operations khi có invariant cụ thể cần quan sát.

### 7.3. Những trạng thái cần thử

- **Lost update**: phép read-modify-write không đồng bộ.
- **Visibility/publication**: reader thấy flag nhưng không thấy payload đúng.
- **Check-then-act**: hai actor cùng kiểm tra điều kiện rồi cùng sửa state trái contract.
- **Unsafe lazy initialization**: một actor publish object khi constructor/state chưa được đồng bộ đúng.
- **Collection concurrency**: add/remove/get đan xen gây trùng/mất item, vi phạm size/invariant.
- **ABA hoặc CAS loop**: thuật toán lock-free xử lý trạng thái đổi từ A→B→A.
- **Lock ordering**: deadlock, livelock hoặc starve; lưu ý test có thể không kết thúc nên cần timeout và kiểm tra thread dump/log.

Không tự xếp mọi race condition vào FORBIDDEN. Thí dụ chương trình cố ý chọn “first winner” có thể chấp nhận nhiều kết quả nhưng yêu cầu nhất quán về mặt contract.

## 8. Đọc báo cáo jcstress đúng cách

Một lần chạy thường cho từng test:

1. Tên test, các JVM configurations/forks và mức độ stress.
2. Danh sách outcome thu được cùng số mẫu (samples), tần suất và xếp loại.
3. Mô tả outcome từ @Outcome(desc = "...").
4. Các cảnh báo về failure, không nhận diện được test, cấu hình JVM không chạy được hoặc test gặp exception.
5. Báo cáo HTML để xem đầy đủ các kết quả, thuận tiện hơn chỉ nhìn vài dòng console.

**Không nên tự chế số liệu.** Ví dụ mô hình báo cáo sau chỉ biểu diễn cách đọc nhãn, không phải stdout/đo đạc thật:

~~~text
Test: LostUpdateTest
Outcome 1  -> ACCEPTABLE_INTERESTING (lost update)
Outcome 2  -> ACCEPTABLE             (both increments observed)
Observed frequencies: [chỉ lấy từ lần chạy thực tế]
~~~

Nếu thấy cả 1 và 2, ví dụ lost update đã được minh họa. Nếu chỉ thấy 2, **chưa chứng minh** code thread-safe. Nếu thấy FORBIDDEN, các bước xử lý gồm tái hiện, giữ log/HTML, xác minh contract và loại bỏ các vấn đề như state shared ngoài chủ ý, annotation sai, initialization không hợp lệ, kết quả ghi đồng thời sai cách.

### 8.1. Sự vắng mặt của một outcome nói lên gì?

Stress testing là lấy mẫu execution có hướng dẫn nhưng vẫn chịu tính ngẫu nhiên/cấu hình. Không quan sát được một kết quả **không phải chứng minh nó bất khả thi**. Trong thực nghiệm, tăng thời gian/forks/CPU variety nâng khả năng tìm một lỗi hiếm, song không thể khảo sát toàn bộ số lịch chạy và trạng thái JMM.

Một lỗi chỉ xảy ra dưới mức tối ưu JIT hoặc kiến trúc CPU khác có thể bị bỏ lỡ trong môi trường hiện tại. Vì vậy kết hợp jcstress với **lập luận happens-before**, contract API, review code và các thử nghiệm khác.

### 8.2. Vì sao số lượng FORBIDDEN cần xác minh?

Một output FORBIDDEN chỉ thực sự có ý nghĩa sau khi xác nhận **oracle kỳ vọng** chính xác. Trường hợp hay nhầm:

- Khai báo một thứ tự actor cố định trong khi không có ordering.
- Giả định volatile bảo đảm tính nguyên tử cho x++.
- Giả định synchronized trên hai object khác nhau bảo vệ cùng một state.
- Arbiter truy cập mutable static state không thuộc vòng đời một lượt test.
- Các actor thực hiện thao tác I/O/timeout và kết quả bị ảnh hưởng bởi ngoại lệ ngoài ý định.
- Test đọc nhiều trường không có đồng bộ và suy luận theo snapshot nguyên tử dù không có contract đó.

Hãy tối giản tái hiện trước; phân biệt bug trong code được kiểm, bug trong test, bug công cụ và bug JVM/hardware.

## 9. So sánh jcstress với JUnit, JMH và các công cụ JVM

| Công cụ | Vấn đề chính | Có thể suy ra điều gì? | Giới hạn |
|---|---|---|---|
| JUnit | Test chức năng, contract với input thông thường | Kết quả một số scenario xác định | Thread interleaving hiếm thường bị bỏ lỡ |
| jcstress | Concurrent correctness, outcomes theo JMM/API | Đã quan sát outcome hợp lệ/hiếm/bị cấm trong điều kiện thử | Không chứng minh tuyệt đối khi không thấy bug, không thay benchmark |
| JMH | Microbenchmark throughput/latency với harness chuyên dụng | So sánh performance của workload được benchmark | Chạy nhanh không chứng minh thread-safe |
| JFR | JVM event recording/profile contention/allocations/CPU | Dấu vết, hotspot, các wait/monitor events khi được ghi | Không tự phân loại JMM outcomes |
| jstack/jcmd Thread.print | Snapshot thread state/stack | Chỗ chờ, deadlock, call stack ở thời điểm lấy mẫu | Không bao phủ mọi interleaving |
| ThreadMXBean | Thread/CPU time/blocked/waited counters nếu JVM hỗ trợ | Gợi ý contention và thời gian chờ | Không phải oracle cho race hoặc linearizability |

### Case: AtomicInteger đúng nhưng vẫn chậm

Nếu AtomicIncrementTest chỉ trả outcome 2, code tránh lost update. Dù vậy 100 thread cùng cập nhật **một AtomicInteger** có thể gây contention tại cùng cache line; mức CPU/cache giao tiếp có thể làm throughput kém so với chia shard.

Câu hỏi “có đúng không?” dùng jcstress và lập luận API; câu hỏi “có nhanh không?” dùng benchmark và profiling. **Không dùng histogram frequencies của jcstress để suy ra throughput/latency production.**

### Case: synchronized chặn race nhưng gây lock contention

Một lock chung bảo vệ đúng invariant có thể là lựa chọn tốt dù throughput giảm; tối ưu đòi hỏi trade-off đúng đắn và hiệu năng. Để biết vùng nào tranh khóa, kết hợp JFR JavaMonitorEnter/ThreadPark và load test thích hợp. Không tháo synchronized chỉ vì thread dump có BLOCKED.

## 10. Quy trình làm việc đáng tin cậy

### Bước A — viết contract và lý do từng outcome

Tạo bảng ngắn trước khi viết code:

| Outcome | Giải thích theo JMM hoặc API | Có được phép? |
|---|---|---|
| Cả hai increment được ghi nhận | Hai actor hoàn tất và atomic update hoạt động | Có |
| Mất một increment trong bản ++ thường | Read-modify-write có thể đan xen | Có theo chương trình racy, nhưng có thể là bug nghiệp vụ |
| Mất một increment trong bản AtomicInteger | Contradicts atomic operation contract | Không |

Nếu không thể giải thích từng outcome, chưa nên dán nhãn FORBIDDEN.

### Bước B — rút nhỏ test, cô lập shared state

Hạn chế mỗi actor vài thao tác, không thêm logging, sleep, network, database, synchronized hoặc println vào race test khi những thứ đó không thuộc hành vi cần kiểm. Logging và sleep có thể thêm ordering hoặc làm thay đổi timing, khiến lỗi biến mất.

Không dùng random seed/time-dependent global trong actor nếu chưa kiểm soát. Tránh kết quả phụ thuộc vào việc hai actor lặp mãi hoặc các thread phụ còn tồn tại sau state kết thúc.

### Bước C — chạy mức nhanh rồi mở rộng có chủ đích

~~~bash
mvn clean verify
java -jar target/jcstress.jar -t '.*PublicationTest' -m quick
~~~

Khi cần thêm độ tin cậy, xem trợ giúp của harness để chọn mode dài hơn, điều chỉnh số forks, CPU affinity, JVM options và thời gian. Chạy đa dạng JDK/CPU khi có thể. Lưu thông tin môi trường và log cho mỗi lần chạy; sự khác biệt kết quả trên hai máy không tự động là lỗi của máy nào.

### Bước D — xử lý bất thường

1. Kiểm tra test đúng package, tên filter đúng, class được annotation processor đưa vào JAR hay chưa.
2. Đọc HTML report, ghi lại test, outcome, count, JVM, mode, options, machine.
3. Lập luận lại happens-before và ordering; ghi cả lịch tương tác được cho là gây kết quả.
4. Rút gọn code; thay hệ thống thật bằng một class state nhỏ với hai actor.
5. Chạy lại dưới nhiều điều kiện. Nếu còn FORBIDDEN, kiểm tra library/JVM/hardware có liên quan sau khi loại lỗi oracle/test.
6. Chỉ kết luận “bug được tái hiện” khi kết quả thực tế và contract đã được xác minh.

### Bước E — đưa stress test vào CI

Có thể chạy nhóm test nhỏ với preset quick như **smoke signal** trong CI, đồng thời dành lịch chạy dài hơn (nightly/periodic) cho race hiếm. Một lần CI xanh là bằng chứng “không thấy outcome bị cấm trong mẫu đã thử”, **không phải bằng chứng tuyệt đối về thread safety**.

Đối với test có khả năng treo do deadlock/livelock, đặt timeout job và thu thread dumps sau khi timeout; cân đối resources vì jcstress có thể chạy nhiều forks trong thời gian dài.

## 11. Câu hỏi thường gặp và lỗi phổ biến

**Tôi có thể chạy jcstress chỉ với java/javac không?** Không đủ; annotations, harness và bước tạo test registry đến từ jcstress artifacts/build. Dùng Maven archetype hoặc build tích hợp tương đương.

**Có cần dùng Spring hay một framework async không?** Không. Các ví dụ này chỉ dùng Java/JDK concurrency, plus công cụ jcstress bên ngoài JDK.

**Vì sao test được đánh dấu @JCStressTest nhưng không xuất hiện trong -t?** Kiểm tra đường dẫn package/class, module Maven, annotation processor, build log và filter. JAR jcstress cần chứa danh sách test đã được processor sinh, không chỉ .class files.

**Nếu một test luôn trả về outcome hợp lệ, có thể kết luận thread-safe?** Chỉ kết luận chưa thấy vi phạm trong các executions đã thử. Kết luận thread-safe phải dựa thêm vào contract, JMM, thuật toán và phạm vi tất cả operations.

**Tôi muốn tạo race bằng Thread.sleep(1) có được không?** Sleep có thể dùng trong ứng dụng thật, nhưng thêm vào litmus dễ thay đổi interleaving/scheduling, không cho bảo đảm. Ưu tiên cấu trúc hai actor nhỏ, để harness tạo đa dạng execution.

**Tôi có cần phân biệt ACCEPTABLE với ACCEPTABLE_INTERESTING?** Cả hai đều là kết quả được phép theo oracle, nhưng loại thứ hai được tô nổi để phân tích. Không tự biến ACCEPTABLE_INTERESTING thành lỗi harness.

**Tôi có thể kiểm tra throughput tăng dưới contention bằng jcstress?** Đây không phải mục đích chính; hãy dùng JMH hoặc load test. jcstress giúp xác minh việc thay lock bằng cơ chế tối ưu có còn đúng contract không.

**Nếu @Arbiter thấy final state đúng, mọi operation trước đó có linearizable?** Không. Final state đúng có thể che intermediate state/return values sai. Muốn kiểm tra linearizability cần thiết kế result ghi lại đủ history hoặc các điều kiện tương ứng.

**Volatile có sửa lost update không?** Không. Volatile giúp visibility/ordering; increment gồm nhiều bước. Dùng atomic update hoặc synchronization phù hợp.

**Chương trình có race, nhưng jcstress không thấy “0” trong PlainPublicationTest?** Điều này hoàn toàn có thể. Test nhạy với JIT/hardware/mode và một số allowed outcomes rất hiếm. Không thấy không có nghĩa plain fields đã an toàn.

## 12. Bài tập luyện tập có hướng dẫn

### Bài 1 — x++ thường và AtomicInteger

Chạy hai test mục 5 trên cùng máy và thêm một máy/JDK khác nếu có. Ghi:

~~~text
JDK / CPU / OS:
jcstress version / mode:
LostUpdateTest: observed outcomes:
AtomicIncrementTest: observed outcomes:
Có FORBIDDEN outcome?:
Diễn giải theo tính nguyên tử của update:
~~~

Kết luận phải tách biệt: “đã quan sát lost update” nếu thấy outcome 1; “chưa quan sát” nếu chưa thấy. Không dự đoán trước frequency.

### Bài 2 — message passing

Chạy PlainPublicationTest và VolatilePublicationTest. Vẽ happens-before graph:

~~~text
Writer: data=42 -> ready=true (volatile write)
                         |
                         | synchronizes-with
                         v
Reader:                  ready (volatile read) -> data read
~~~

Giải thích tại sao việc reader thấy ready true trong phiên bản volatile đòi hỏi payload 42, trong khi bản plain thiếu đồng bộ không có kết luận tương tự.

### Bài 3 — bài toán check-then-act

Hãy thiết kế class state chứa biến boolean acquired và method tryAcquire không đồng bộ:

~~~java
boolean acquired;

boolean tryAcquire() {
    if (!acquired) {
        acquired = true;
        return true;
    }
    return false;
}
~~~

Đây chỉ là **mảnh code minh họa**. Hai actor cùng gọi method và mỗi actor ghi kết quả boolean vào một field riêng của result holder. Bạn có chấp nhận outcome “cả hai đều true” không? Nếu contract là “chỉ một người giành quyền”, **không**. Hãy thay check-then-act bằng AtomicBoolean.compareAndSet(false, true), rồi xác định lại các outcome hợp lệ trước khi chạy.

### Bài 4 — phân biệt correctness và contention

Giả định bạn viết một bộ đếm dùng synchronized và một bộ đếm dùng AtomicInteger, cả hai đều qua jcstress. Điều đó **chưa** trả lời bộ nào nhanh hơn. Thiết kế tiếp một phép JMH với nhiều thread, công việc giữ nguyên, kết quả được quan sát, so sánh throughput cùng phân phối latency/CPU nếu thích hợp. Viết rõ điều kiện test trước khi kết luận.

## 13. Ghi nhớ

- **jcstress** là harness kiểm tra concurrency correctness theo các trạng thái kết quả, không có sẵn trong JDK.
- **@Actor** mô phỏng các hoạt động cạnh tranh; **@Arbiter** quan sát trạng thái sau actor; **@Outcome** là oracle được người viết test khai báo.
- **ACCEPTABLE_INTERESTING** được phép nhưng đáng phân tích; **FORBIDDEN** cần rà soát nghiêm túc cả code và oracle.
- **Không thấy bug trong một lần stress** không chứng minh không có bug.
- **Contention** có thể tồn tại trong code hoàn toàn đúng. jcstress xác minh contract, JMH/JFR và các công cụ đo khác giúp phân tích chi phí contention.
- Khi có vấn đề với Java Memory Model, hãy lập luận bằng **happens-before/atomicity/ordering**, không chỉ dựa vào tần suất observed outcomes.

**Nguồn chính thức để tra cứu và đối chiếu:** [OpenJDK jcstress project](https://openjdk.org/projects/code-tools/jcstress/), [OpenJDK jcstress GitHub README](https://github.com/openjdk/jcstress/blob/master/README.md), [jcstress samples](https://github.com/openjdk/jcstress/tree/master/jcstress-samples), [Java Language Specification §17 Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html), [java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html).
