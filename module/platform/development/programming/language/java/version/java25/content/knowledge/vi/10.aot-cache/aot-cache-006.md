# Vai trò của ahead-of-time method profiling trong việc làm nóng mã

## 1. Bài toán: vì sao ứng dụng Java cần warm-up?

Khi một ứng dụng Java vừa khởi động, HotSpot chưa biết chính xác phương thức nào sẽ được gọi thường xuyên, nhánh điều kiện nào chiếm ưu thế, kiểu đối tượng nào xuất hiện tại các điểm gọi đa hình và phương thức nào đáng được tối ưu mạnh. JVM bắt đầu thực thi bytecode, thu thập dữ liệu trong lúc chạy rồi dùng **Just-in-Time compiler (JIT)** để biên dịch các phương thức nóng thành mã máy tối ưu.

Quá trình đó tạo nên **warm-up**. Với ứng dụng chạy lâu, chi phí này có thể được che khuất sau khi hệ thống ổn định. Với ứng dụng CLI chạy vài giây, function-as-a-service, container thường xuyên scale từ zero hoặc tiến trình phải khởi động lại liên tục, warm-up có thể chiếm tỷ lệ lớn trong thời gian phục vụ yêu cầu đầu tiên.

**Ahead-of-Time Method Profiling (JEP 515)** được hoàn thiện trong **Java 25** để cải thiện quá trình này. Trong lần chạy huấn luyện (**training run**), JVM thu thập **method execution profiles** và lưu chúng vào **AOT cache**. Ở lần chạy sau, JIT có thể đọc các profile đã thu thập ngay từ đầu, nhận diện phương thức nóng sớm hơn và bắt đầu tối ưu trước khi phải chờ một lượng lớn dữ liệu profiling mới.

Bài **Vai trò của ahead-of-time method profiling trong việc làm nóng mã**, thuộc chương **AOT cache** của lộ trình **JAVA_VERSION_JAVA25**, hướng dẫn:

1. Phân biệt profiling, AOT cache, AOT method profiling và JIT compilation.
2. Hiểu JEP 515 bổ sung gì cho AOT cache vốn đã có từ Java 24.
3. Tạo cache bằng quy trình đơn giản của Java 25 và tái sử dụng ở lần chạy production.
4. Thiết kế training workload đủ đại diện để profile hữu ích.
5. Đánh giá startup, warm-up và hiệu năng ổn định bằng phép đo có thể lặp lại.
6. Kiểm tra tính tương thích của cache với artifact, JDK, hệ điều hành và CPU.

**Phạm vi phiên bản:** ví dụ dùng HotSpot của **JDK 25**. JEP 515 đã là tính năng hoàn thiện, không cần preview flag hoặc thay đổi mã nguồn ứng dụng. JEP 483 đưa AOT cache vào JDK 24; JEP 514 đơn giản hóa thao tác tạo cache trong JDK 25; JEP 515 đưa method profiles vào cache để cải thiện warm-up.

## 2. Phân biệt profiling, AOT và JIT

Các thuật ngữ có liên quan nhưng không đồng nghĩa:

| Khái niệm | Thời điểm | Vai trò |
| --- | --- | --- |
| **Runtime profiling** | Khi ứng dụng đang chạy | JVM quan sát tần suất gọi, kiểu receiver, nhánh và hành vi thực thi để quyết định tối ưu. |
| **JIT compilation** | Trong lúc chạy | Biên dịch bytecode thành mã máy khi JVM có đủ dữ liệu và quyết định phương thức cần tối ưu. |
| **AOT cache** | Tạo trước một lần chạy production | Lưu các artifact AOT có thể tái sử dụng, như dữ liệu lớp đã nạp/liên kết, đối tượng được cache và method profiles trong Java 25. |
| **AOT method profiling (JEP 515)** | Training trước production và nạp lại khi khởi động | Mang dữ liệu profiling của lần training sang lần chạy sau để JIT có thông tin sớm. |
| **AOT compilation** | Tùy công nghệ/runtime | Biên dịch mã trước khi ứng dụng chạy. Đây không phải điều JEP 515 tự thực hiện đối với mọi phương thức Java. |

~~~mermaid
flowchart TD
    A["Training run trên workload đại diện"] --> B["HotSpot thực thi và thu thập method profiles"]
    A --> C["Nạp lớp và tạo các artifact AOT khác"]
    B --> D["AOT cache"]
    C --> D
    D --> E["Production run nạp cache"]
    E --> F["JIT có profile từ sớm"]
    F --> G["Biên dịch và tối ưu phương thức nóng sớm hơn"]
    G --> H["Runtime profiling vẫn tiếp tục"]
    H --> I["JIT điều chỉnh theo workload thực tế"]
~~~

**Điểm cốt lõi:** JEP 515 lưu **dữ liệu mô tả hành vi thực thi**, không biến toàn bộ ứng dụng thành native executable. JIT vẫn hoạt động ở runtime, vẫn quan sát hành vi mới và vẫn có thể thay đổi quyết định khi workload thực tế khác training.

## 3. Method profile chứa thông tin gì?

Khi một phương thức được thực thi, HotSpot có thể thu thập các thống kê phục vụ compiler. Tùy loại điểm thực thi, thông tin có thể giúp JVM hiểu:

- Phương thức được gọi thường xuyên đến mức nào.
- Một call site đa hình thường nhận đối tượng thuộc kiểu nào.
- Nhánh điều kiện nào thường được đi qua.
- Hành vi vòng lặp và các điểm gọi nào có cơ hội tối ưu.
- Những phương thức nào trở nên nóng và đáng được compiler ưu tiên.

Không nên coi method profile là bản ghi log chi tiết của mọi lời gọi. Đây là dữ liệu thống kê nội bộ phục vụ quyết định tối ưu của HotSpot; ứng dụng không cần tự tạo đối tượng profile hay gọi API riêng để ghi các thống kê này.

Ví dụ, một dịch vụ có đường xử lý chính:

~~~text
HTTP request
  -> OrderService.place()
      -> PricingService.calculate()
          -> DiscountPolicy.apply()
      -> InventoryService.reserve()
~~~

Nếu training workload chủ yếu gọi luồng đặt hàng tiêu chuẩn, JVM có thể ghi nhận các phương thức và call site quan trọng của luồng đó. Khi production khởi động bằng cache, JIT có dữ liệu này sớm hơn để ưu tiên tối ưu các đường thực thi thường gặp.

Nếu training chỉ chạy health check mà không gọi OrderService.place(), profile có thể không phản ánh đường nghiệp vụ quan trọng. Cache vẫn có thể chứa thông tin lớp và các artifact khác, nhưng lợi ích của method profiling cho đường đặt hàng sẽ bị hạn chế.

### Profile là gợi ý có căn cứ, không phải hợp đồng cố định

Training chỉ quan sát một mẫu workload tại một thời điểm. Nếu production có tỷ lệ request, kiểu dữ liệu hoặc nhánh xử lý khác, profile cũ có thể không còn là dự đoán tốt. JVM vẫn tiếp tục profiling ở runtime và có thể điều chỉnh tối ưu dựa trên hành vi mới; profile AOT không khóa ứng dụng vào một đường chạy.

## 4. JEP 515 bổ sung gì cho AOT cache?

**JDK 24 – JEP 483: Ahead-of-Time Class Loading & Linking** đưa AOT cache vào HotSpot. Cache giúp tái sử dụng một số công việc đã thực hiện trước đó, đặc biệt là đọc, phân tích, nạp và liên kết lớp; cache cũng có thể chứa các đối tượng được chuẩn bị trước.

**JDK 25 – JEP 515: Ahead-of-Time Method Profiling** mở rộng workflow này bằng cách đưa method execution profiles từ training run vào AOT cache. Khi production run nạp cache, JIT có thể tiếp cận dữ liệu profile từ lần trước ngay từ đầu thay vì phải đợi chương trình chạy đủ lâu để tự thu thập lại.

| Phiên bản | Thành phần liên quan | Ý nghĩa đối với startup/warm-up |
| --- | --- | --- |
| **JDK 24 – JEP 483** | AOT class loading và linking, AOT cache | Giảm một phần công việc khởi động bằng cách tái sử dụng artifact lớp và đối tượng được cache. |
| **JDK 25 – JEP 514** | AOT command-line ergonomics | Đơn giản hóa quy trình tạo cache, có thể training và assembly qua một lệnh. |
| **JDK 25 – JEP 515** | AOT method profiling | Đưa profile của lần training vào cache để JIT bắt đầu tối ưu sớm hơn. |
| **JDK 26 – JEP 516** | AOT object caching with any GC | Mở rộng khả năng cache đối tượng AOT cho mọi garbage collector, gồm ZGC. Đây là cải tiến phiên bản sau Java 25. |

**Không gán nhầm kết quả:** nếu so ứng dụng không dùng cache với ứng dụng dùng cache Java 25, khác biệt có thể đến từ cả dữ liệu lớp/đối tượng lẫn method profiles. Không nên kết luận toàn bộ phần cải thiện đo được là riêng JEP 515 nếu thí nghiệm chưa tách được các yếu tố đó.

## 5. AOT cache cải thiện startup và warm-up theo cách nào?

Có hai loại thời gian cần phân biệt:

- **Startup time:** từ lúc tiến trình được khởi chạy đến khi ứng dụng sẵn sàng nhận công việc hoặc hoàn thành đơn vị công việc đầu tiên.
- **Warm-up time:** khoảng thời gian ứng dụng cần để đạt trạng thái hiệu năng gần ổn định sau khi khởi động.

Không có cache, JVM phải tự nạp/liên kết lớp và thu thập profile trong lần chạy hiện tại. Với cache, một số công việc nạp lớp đã được chuẩn bị từ trước, còn method profiles giúp JIT biết sớm những phương thức có khả năng nóng.

~~~mermaid
flowchart LR
    A["Khởi động JVM"] --> B["Nạp ứng dụng"]
    B --> C["Thực thi ban đầu"]
    C --> D["Thu profile runtime"]
    D --> E["Nhận diện phương thức nóng"]
    E --> F["JIT biên dịch / tối ưu"]
    F --> G["Hiệu năng ổn định"]
~~~

~~~mermaid
flowchart LR
    A["Khởi động JVM + nạp AOT cache"] --> B["Có sẵn class artifacts và method profiles"]
    B --> C["JIT có thể ưu tiên phương thức nóng sớm"]
    C --> D["Runtime tiếp tục quan sát và điều chỉnh"]
    D --> E["Hiệu năng ổn định sớm hơn nếu profile phù hợp"]
~~~

**AOT method profiling không loại bỏ toàn bộ warm-up.** Vẫn có thể cần khởi tạo kết nối, nạp dữ liệu, tạo thread, cấp phát đối tượng, biên dịch mã chưa có profile hoặc xử lý workload chưa xuất hiện khi training. Lợi ích chính là giảm thời gian JIT phải tự khám phá lại hành vi của những đường thực thi đã được training.

Một ứng dụng có thể cải thiện time-to-first-request và đạt throughput ổn định sớm hơn, nhưng mức cải thiện phụ thuộc workload, JDK build, phần cứng, GC, cấu hình heap và tính đại diện của training.

## 6. Tạo AOT cache trong Java 25 bằng một lệnh

JEP 514 giúp đơn giản hóa quy trình phổ biến. Với ứng dụng đã đóng gói thành JAR:

~~~bash
# Training run và assembly trong một workflow
java -XX:AOTCacheOutput=app.aot -jar app.jar
~~~

Khi ứng dụng chạy, hãy thực hiện workload đại diện. Khi tiến trình kết thúc, JVM hoàn tất việc ghi cache và thực hiện bước assembly cần thiết. Sau đó dùng cache ở lần chạy tiếp theo:

~~~bash
# Production run sử dụng cache đã tạo
java -XX:AOTCache=app.aot -jar app.jar
~~~

Với ứng dụng chạy bằng classpath:

~~~bash
# Training
java -XX:AOTCacheOutput=app.aot -cp app.jar com.example.App

# Production
java -XX:AOTCache=app.aot -cp app.jar com.example.App
~~~

Các tham số **-XX:AOTCacheOutput** và **-XX:AOTCache** là hai lựa chọn cho hai giai đoạn khác nhau; **không truyền đồng thời cả hai** trong cùng một lệnh. Phần mở rộng thường dùng cho cache là **.aot**.

### 6.1. Training một dịch vụ HTTP

Với ứng dụng server, training run có thể kéo dài trong khi bạn gửi request từ một công cụ kiểm thử khác:

1. Khởi chạy ứng dụng với **-XX:AOTCacheOutput=build/aot/app.aot**.
2. Đợi server hoàn tất startup.
3. Gửi một workload đại diện từ máy kiểm thử hoặc script.
4. Bao phủ các đường xử lý chính, nhánh phổ biến và những loại request có ý nghĩa.
5. Dừng ứng dụng một cách có kiểm soát để JVM hoàn tất việc tạo cache.
6. Khởi chạy lại cùng artifact với **-XX:AOTCache=build/aot/app.aot**.

Ví dụ lệnh khởi chạy:

~~~bash
java -XX:AOTCacheOutput=build/aot/app.aot -jar build/libs/app.jar
~~~

Sau khi server sẵn sàng, gửi request bằng công cụ của dự án. Ví dụ:

~~~bash
curl -X POST http://localhost:8080/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"SKU-1","quantity":2}'
~~~

Request chỉ là minh họa; thay bằng endpoint và payload hợp lệ của ứng dụng. Không dùng dữ liệu production nhạy cảm hoặc training trực tiếp trên hệ thống đang phục vụ khách hàng nếu thao tác đó có thể tạo đơn hàng, gửi email, thanh toán hay gây side effect không mong muốn.

### 6.2. Lưu ý tài nguyên của chế độ một lệnh

Với **-XX:AOTCacheOutput**, JVM thực hiện training và sau đó khởi chạy một JVM thứ hai cho bước assembly. JVM thứ hai có thể dùng heap riêng với kích thước tương đương heap của training run. Vì vậy, môi trường có giới hạn bộ nhớ cần dự trù thêm tài nguyên; một lệnh tạo cache có thể cần gần gấp đôi heap đã cấu hình trong giai đoạn assembly.

Nếu môi trường training nhỏ hoặc container có memory limit chặt, hãy cân nhắc tách training và assembly thành hai bước. Có thể training trên môi trường gần production rồi assembly trên máy build có thêm CPU/RAM, miễn tuân thủ các yêu cầu tương thích của AOT cache.

## 7. Quy trình tách riêng training, assembly và production

Java 25 vẫn hỗ trợ workflow tường minh khi cần kiểm soát từng giai đoạn:

~~~bash
# 1. Training: thực thi ứng dụng và ghi thống kê
java -XX:AOTMode=record \
     -XX:AOTConfiguration=app.aotconf \
     -jar app.jar
~~~

Thực hiện workload đại diện trong tiến trình training và dừng ứng dụng có kiểm soát. Sau đó tạo cache:

~~~bash
# 2. Assembly: đọc cấu hình training và ghi cache
java -XX:AOTMode=create \
     -XX:AOTConfiguration=app.aotconf \
     -XX:AOTCache=app.aot \
     -cp app.jar
~~~

Giai đoạn assembly không thực thi ứng dụng. Nó sử dụng dữ liệu thu được từ training để tạo AOT cache.

~~~bash
# 3. Production: chạy ứng dụng với cache
java -XX:AOTCache=app.aot -jar app.jar
~~~

| Giai đoạn | Cờ chính | Kết quả |
| --- | --- | --- |
| Training | **-XX:AOTMode=record**, **-XX:AOTConfiguration=...** | Tệp cấu hình .aotconf chứa dữ liệu training. |
| Assembly | **-XX:AOTMode=create**, **-XX:AOTConfiguration=...**, **-XX:AOTCache=...** | Tệp AOT cache .aot. |
| Production | **-XX:AOTCache=...** | Ứng dụng nạp cache và tận dụng các artifact tương thích. |

Với quy trình phổ biến, **JEP 514 cho phép dùng -XX:AOTCacheOutput để gộp training và assembly**. Quy trình tách riêng vẫn hữu ích khi cần phân bổ tài nguyên khác nhau, lưu trữ configuration artifact hoặc điều tra lỗi tạo cache.

### AOTMode và hành vi khi cache không dùng được

| Chế độ | Hành vi |
| --- | --- |
| **auto** | Mặc định. Nếu có AOTCacheOutput thì thực hiện training/assembly; nếu có cache đọc được thì dùng cache; nếu không có cache phù hợp thì chạy bình thường. |
| **record** | Thực hiện training và ghi AOT configuration. |
| **create** | Assembly cache từ AOT configuration; không chạy ứng dụng. |
| **on** | Yêu cầu cache được nạp; nếu không tương thích, JVM báo lỗi và dừng. |
| **off** | Tắt việc dùng AOT cache. |

Trong production, chế độ mặc định **auto** thường an toàn hơn vì nếu cache không đọc được, ứng dụng vẫn có thể chạy mà không hưởng lợi từ cache. Chế độ **on** hữu ích để kiểm tra fail-fast trong CI hoặc khi chẩn đoán tương thích, không nên bật tùy tiện nếu yêu cầu vận hành là ứng dụng phải tiếp tục chạy khi cache không dùng được.

Để xem lý do cache được dùng hay bị bỏ qua:

~~~bash
java -XX:AOTCache=app.aot -XX:AOTMode=auto -Xlog:aot -jar app.jar
~~~

Để kiểm tra fail-fast:

~~~bash
java -XX:AOTCache=app.aot -XX:AOTMode=on -Xlog:aot -jar app.jar
~~~

## 8. Thiết kế training workload để method profile có ích

Chất lượng method profile phụ thuộc trực tiếp vào những gì training run thực sự thực thi. Một training run chỉ khởi động ứng dụng rồi thoát có thể ghi nhận đường startup, nhưng chưa chắc phản ánh các đường nghiệp vụ nóng.

### Những đường nên bao phủ

- **Startup path:** nạp cấu hình, tạo bean, đăng ký handler, mở kết nối cần thiết.
- **Happy path:** request hoặc tác vụ phổ biến nhất.
- **Hot service path:** các phương thức được gọi thường xuyên trong xử lý nghiệp vụ.
- **Polymorphic call sites:** những điểm gọi có thể nhận nhiều implementation hoặc kiểu đối tượng.
- **Branch phổ biến:** nhánh điều kiện chiếm phần lớn traffic thực tế.
- **Serialization/parsing:** JSON, XML, protocol hoặc mapping nếu chúng nằm trên đường nóng.
- **Error path có tần suất thực tế:** chỉ bao phủ khi lỗi đó là một phần workload vận hành thường gặp và an toàn để mô phỏng.

Không cần cố gắng thực thi mọi nhánh hiếm hoặc toàn bộ test suite trong training. Nạp quá nhiều lớp và thư viện không cần thiết có thể làm cache lớn hơn mà không cải thiện đường thực thi quan trọng.

### Ví dụ phân loại workload

| Kịch bản | Tỷ lệ giả định | Mục đích |
| --- | ---: | --- |
| Tra cứu đơn hàng | 55% | Bao phủ đường đọc thường gặp. |
| Tạo đơn hàng | 25% | Bao phủ validation, pricing và persistence. |
| Hủy đơn hàng | 10% | Bao phủ cập nhật trạng thái. |
| Đơn hàng có khuyến mãi | 8% | Bao phủ nhánh pricing bổ sung. |
| Input không hợp lệ | 2% | Bao phủ error handling phổ biến. |

Các tỷ lệ là ví dụ để lập kế hoạch, không phải phân bố chuẩn cho mọi hệ thống. Hãy lấy tỷ lệ từ dữ liệu vận hành đã được tổng hợp và loại bỏ thông tin nhận diện người dùng.

### Training cho ứng dụng server và ứng dụng batch

**Server:** giữ tiến trình chạy trong thời gian training, gửi request theo kịch bản đại diện, rồi dừng có kiểm soát để tạo cache.

**Batch:** chạy một hoặc nhiều batch có kích thước và phân bố dữ liệu gần production. Không dùng tập dữ liệu quá nhỏ nếu nó khiến các nhánh xử lý chính không được thực thi.

**CLI ngắn hạn:** thực thi nhiều lần đường xử lý quan trọng trong training nếu điều đó phản ánh hành vi thực tế của ứng dụng. Với một tiến trình vốn chỉ chạy một tác vụ rất ngắn, cần đo xem chi phí tạo và nạp cache có đáng với phần warm-up tiết kiệm hay không.

## 9. Ví dụ nhỏ: tạo cache cho một chương trình có hot method

Ví dụ sau có một phương thức được gọi lặp lại nhiều lần và một phương thức chỉ được gọi khi có tham số phụ:

~~~java
public final class HotPathDemo {

    private static long hotMethod(long value) {
        return (value * 31 + 17) ^ (value >>> 3);
    }

    private static long occasionalMethod(long value) {
        return value * value + 101;
    }

    public static void main(String[] args) {
        int iterations = args.length == 0
                ? 2_000_000
                : Integer.parseInt(args[0]);

        long checksum = 0;
        for (int i = 0; i < iterations; i++) {
            checksum += hotMethod(i);
        }

        if (args.length > 1 && "--occasional".equals(args[1])) {
            checksum += occasionalMethod(iterations);
        }

        System.out.println("checksum=" + checksum);
    }
}
~~~

Biên dịch và đóng gói:

~~~bash
mkdir -p out
javac --release 25 -d out HotPathDemo.java
jar --create --file hotdemo.jar --main-class HotPathDemo -C out .
~~~

Tạo cache với workload thường xuyên gọi hotMethod:

~~~bash
java -XX:AOTCacheOutput=hotdemo.aot -jar hotdemo.jar 2000000
~~~

Chạy lại bằng cache và cùng workload:

~~~bash
java -XX:AOTCache=hotdemo.aot -jar hotdemo.jar 2000000
~~~

Nếu production thường xuyên dùng nhánh **--occasional**, training cũng cần thực thi nhánh đó:

~~~bash
java -XX:AOTCacheOutput=hotdemo-full.aot \
     -jar hotdemo.jar 2000000 --occasional
~~~

Sau đó dùng cache được tạo với cùng kiểu tham số:

~~~bash
java -XX:AOTCache=hotdemo-full.aot \
     -jar hotdemo.jar 2000000 --occasional
~~~

Đây là ví dụ minh họa cách cung cấp workload khác nhau. Một method profile được ghi nhận khi phương thức thực sự được thực thi; nếu training không gọi occasionalMethod, không nên kỳ vọng profile của phương thức đó phản ánh đúng hành vi production.

**Không kết luận hiệu năng từ một lần chạy.** Chương trình này chủ yếu giúp hiểu quy trình. Để đo có ý nghĩa, cần nhiều lần chạy độc lập, kiểm soát CPU/GC/heap, tránh các tiến trình cạnh tranh và so sánh cả startup lẫn các vòng lặp sau startup.

## 10. Cache tương thích với ứng dụng và môi trường nào?

AOT cache không phải artifact dùng chung cho mọi JAR và mọi máy. Cache gắn với:

1. **Ứng dụng:** cách ứng dụng được biểu diễn bằng classpath, JAR hoặc module path.
2. **JDK release:** cache được tạo cho một bản phát hành JDK cụ thể.
3. **Hệ điều hành và kiến trúc CPU:** cache phụ thuộc nền tảng.

Khi rebuild ứng dụng, thay đổi dependency, đổi JDK release hoặc chuyển OS/CPU architecture, hãy tạo cache mới. Trong quy trình release, nên xem file .aot là artifact được tạo cho đúng application build và runtime target, không phải file cache dùng chung lâu dài.

### Những điều cần giữ nhất quán

| Thành phần | Yêu cầu thực tế |
| --- | --- |
| JAR ứng dụng | Training và production dùng cùng artifact đã build. |
| Dependency JAR | Giữ cùng tập dependency và thứ tự classpath; nếu thay đổi thì tạo cache mới. |
| Timestamp JAR | Giữ timestamp ổn định giữa training và production theo yêu cầu cache. |
| Classpath | Dùng danh sách JAR rõ ràng; tránh directory, wildcard và nested JAR trong workflow AOT. |
| JDK | Dùng cùng JDK release cho training, assembly và production; nên khóa cùng distribution/build đã kiểm chứng. |
| OS/CPU | Tạo cache riêng cho từng nền tảng đích. |
| JVM options | Giữ các tùy chọn ảnh hưởng class loading, module path và cấu hình runtime tương thích. |
| Application behavior | Training nên mô phỏng đường thực thi production. |

Production classpath phải tương thích với classpath training; thực hành an toàn nhất là giữ nguyên danh sách và thứ tự JAR. Nếu cần bổ sung dependency hoặc đổi cách đóng gói, hãy tạo lại cache theo artifact mới thay vì dựa vào khả năng tương thích ngoài dự kiến.

### Không dùng cache cũ sau khi phát hành bản mới

Ví dụ release app-1.4.0.jar có cache app-1.4.0.aot. Khi chuyển sang app-1.4.1.jar, hãy training và tạo cache app-1.4.1.aot mới. Đổi tên JAR mà nội dung khác, thêm thư viện hoặc thay đổi classpath vẫn là thay đổi ứng dụng; đổi tên file không làm cache tương thích trở lại.

## 11. Giới hạn theo garbage collector trong Java 25

Một chi tiết quan trọng khi áp dụng AOT cache trên Java 25: **AOT object caching của JDK 24/25 chưa hỗ trợ ZGC**. Vấn đề nằm ở cách biểu diễn và nạp trạng thái heap object đã cache, vốn gắn với định dạng bộ nhớ của một số garbage collector.

**JDK 26 – JEP 516: Ahead-of-Time Object Caching with Any GC** đã mở rộng cơ chế cache object để hoạt động với mọi garbage collector, bao gồm ZGC. Vì vậy:

- Nếu ứng dụng chạy bằng **JDK 25** và muốn hưởng đầy đủ AOT cache, hãy chọn garbage collector được hỗ trợ cho AOT cache của JDK 25 và xác minh trên đúng vendor build.
- Nếu production cần **ZGC**, đừng lấy khả năng tương thích của JDK 26 áp ngược cho JDK 25.
- Khi nâng lên **JDK 26+**, hãy tạo lại AOT cache theo JDK release mới và kiểm thử lại trên collector mục tiêu.

Giới hạn này thuộc phiên bản runtime, không phải giới hạn vĩnh viễn của ý tưởng AOT method profiling. JEP 515 vẫn là kiến thức Java 25 hiện hành; JEP 516 là cải tiến tiếp nối ở JDK 26.

## 12. Quan sát training và kiểm tra cache có được dùng không

### 12.1. Dùng JFR để hiểu training workload

**JDK Flight Recorder (JFR)** có thể giúp xem lớp nào được nạp và phương thức nào xuất hiện thường xuyên trong recording. JFR là công cụ quan sát; nó **không phải** cơ chế bắt buộc để tạo method profiles trong AOT cache. HotSpot tự thu profile khi thực hiện training.

Ví dụ bật recording:

~~~bash
java -XX:StartFlightRecording=filename=training.jfr,settings=profile \
     -XX:AOTCacheOutput=app.aot \
     -jar app.jar
~~~

Sau khi tiến trình kết thúc và recording được ghi ra, có thể xem các hot methods:

~~~bash
jfr view hot-methods training.jfr
~~~

Để kiểm tra lớp được nạp, có thể dùng sự kiện jdk.ClassLoad hoặc lệnh jfr print phù hợp với recording. Kết quả giúp nhận diện training run đã chạm tới những thành phần nào. Không cần bật JFR trong mọi production run nếu chi phí ghi nhận không phù hợp.

### 12.2. Kiểm tra AOT cache được nạp

Khi chạy production:

~~~bash
java -XX:AOTCache=app.aot -Xlog:aot -jar app.jar
~~~

Trong môi trường test, có thể dùng:

~~~bash
java -XX:AOTCache=app.aot -XX:AOTMode=on -Xlog:aot -jar app.jar
~~~

**AOTMode=on** khiến JVM báo lỗi nếu cache không thể được sử dụng, phù hợp với bước xác minh tương thích. Sau khi xác nhận, production thường nên dùng chế độ mặc định auto để ứng dụng vẫn có thể chạy khi cache không dùng được.

### 12.3. Phân biệt log cache với bằng chứng hiệu năng

Thông báo JVM đã nạp AOT cache chứng minh cache được chấp nhận, **không** chứng minh ứng dụng nhanh hơn. Cần đo startup, warm-up, latency và throughput trên cùng môi trường. Ngược lại, không thấy cải thiện trong một lần chạy cũng chưa chứng minh cache không hoạt động; workload có thể không hưởng lợi từ các artifact đã cache.

## 13. Đánh giá hiệu quả bằng benchmark có kiểm soát

Để đánh giá AOT method profiling, cần đo nhiều khía cạnh:

| Chỉ số | Câu hỏi |
| --- | --- |
| **Time to first useful request** | Bao lâu sau khi process khởi chạy thì request đầu tiên hoàn tất? |
| **Time to readiness** | Bao lâu đến khi ứng dụng sẵn sàng nhận traffic? |
| **Warm-up curve** | Latency/throughput cải thiện như thế nào qua từng khoảng sau startup? |
| **Steady-state throughput** | Sau khi warm-up, lượng công việc xử lý được có thay đổi không? |
| **Latency percentiles** | p50, p95, p99 trong giai đoạn đầu và giai đoạn ổn định khác nhau thế nào? |
| **CPU và memory** | Chi phí tạo cache, nạp cache và vận hành có tăng không? |
| **Cache size** | Method profiles và các artifact khác làm file cache lớn thêm bao nhiêu? |

### Ma trận so sánh tối thiểu

| Biến thể | Mục đích |
| --- | --- |
| **Không dùng AOT cache** | Baseline của JVM chạy bình thường. |
| **Dùng AOT cache từ training đại diện** | Đánh giá lợi ích tổng hợp của AOT cache Java 25, gồm các artifact lớp/đối tượng và method profiles. |
| **Dùng cache từ training nông** | Đánh giá độ nhạy của kết quả với mức độ bao phủ workload; không phải phép tách hoàn toàn riêng JEP 515. |

Không nên so sánh JDK 24 không cache với JDK 25 có cache rồi quy toàn bộ chênh lệch cho JEP 515: JDK, compiler, runtime và cache đã thay đổi cùng lúc. Nếu muốn đánh giá riêng phần method profile, cần thiết kế thử nghiệm có đối chứng và hiểu rõ các tùy chọn chẩn đoán được hỗ trợ ở đúng bản JDK; không dựa vào cờ nội bộ/không được tài liệu hóa trong production.

### Quy tắc benchmark

1. Dùng cùng artifact, dependency, JDK build, OS/CPU, heap, GC và JVM options trong các lần so sánh.
2. Tách thời gian training/assembly khỏi thời gian production startup.
3. Chạy mỗi biến thể nhiều lần, luân phiên thứ tự để giảm ảnh hưởng của cache hệ điều hành và nhiệt độ CPU.
4. Đo từ process mới; không dùng một tiến trình đã warm-up để đại diện startup.
5. Gửi cùng request mix và dữ liệu đầu vào, dùng tải kiểm thử ổn định.
6. Báo cáo median và percentile phù hợp, không chỉ chọn lần chạy nhanh nhất.
7. Ghi rõ cache có được nạp thành công hay không qua -Xlog:aot.
8. Kiểm tra cả latency sau warm-up; mục tiêu là cải thiện thời gian đạt hiệu năng hữu ích mà không gây suy giảm ổn định.

Không có tỷ lệ tăng tốc cố định cho mọi ứng dụng. Một chương trình chạy lâu, ít restart và có startup path nhẹ có thể không thu hồi được chi phí training/cache. Một ứng dụng ngắn hạn, có đường xử lý lặp lại rõ và startup/warm-up chiếm phần lớn thời gian có thể hưởng lợi rõ hơn.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Cache không được tạo sau training | Tiến trình chưa kết thúc, quyền ghi thư mục sai hoặc assembly thất bại. | Kiểm tra shutdown, đường dẫn, quyền ghi và log JVM. |
| AOTMode=on báo cache không tương thích | Khác JDK, artifact, classpath, OS/CPU hoặc JVM options. | Tạo lại cache bằng đúng artifact và runtime target. |
| auto chạy bình thường nhưng không có lợi ích | Cache không được nạp hoặc workload không được training bao phủ. | Bật -Xlog:aot, kiểm tra cache và training path. |
| Startup cải thiện nhưng request đầu vẫn chậm | Đường request chưa được training hoặc còn khởi tạo dependency/I/O. | Bổ sung workload đại diện và đo riêng request đầu. |
| Cache tạo ra nhưng file quá lớn | Training nạp quá nhiều lớp/đường không cần thiết. | Thu gọn training vào startup path và nghiệp vụ chính. |
| Cache không dùng sau rebuild | JAR/dependency/classpath đã đổi. | Sinh cache mới cho đúng artifact build. |
| Cache không dùng sau nâng JDK | Cache gắn với JDK release. | Training và tạo cache lại bằng JDK mới. |
| Kết quả khác giữa máy local và production | OS/CPU, JDK vendor/build hoặc classpath không giống nhau. | Tạo cache theo từng nền tảng và khóa môi trường runtime. |
| Training không có profile của hot method | Workload chưa gọi phương thức hoặc chạy chưa đủ đại diện. | Gửi request/tác vụ bao phủ đường nóng; kiểm tra JFR. |
| Tạo cache một lệnh bị thiếu RAM | Assembly chạy trong JVM thứ hai với heap riêng. | Tách training và assembly hoặc cấp thêm tài nguyên. |
| Ứng dụng dùng ZGC trên JDK 25 không hưởng đầy đủ AOT cache | Hạn chế AOT object caching của JDK 25. | Dùng collector được hỗ trợ cho JDK 25 hoặc đánh giá nâng JDK 26+. |
| Profile không phù hợp sau khi thay traffic | Training workload không còn đại diện. | Training lại theo workload production mới và benchmark lại. |

### Checklist điều tra nhanh

1. Xác nhận runtime là JDK 25 và ghi đầy đủ vendor/build.
2. Xác nhận cache được tạo sau training, không chỉ có file configuration.
3. Kiểm tra artifact, classpath, thứ tự dependency và timestamp JAR.
4. Kiểm tra OS/CPU và garbage collector có phù hợp với bản JDK đang dùng.
5. Dùng -Xlog:aot hoặc AOTMode=on trong môi trường kiểm thử để biết cache có nạp được không.
6. Kiểm tra training đã gọi các phương thức quan trọng chưa.
7. Đo lại trên process mới và cùng workload trước khi kết luận.

## 15. Triển khai AOT cache trong CI/CD

Một pipeline phù hợp có thể tạo cache sau khi build artifact và trước khi đóng gói image:

~~~text
Build application JAR
       |
       v
Create isolated training environment
       |
       v
Run representative workload with AOTCacheOutput
       |
       v
Graceful shutdown and cache assembly
       |
       v
Verify cache with AOTMode=on + Xlog:aot
       |
       v
Benchmark smoke test
       |
       v
Package matching JAR + matching AOT cache
       |
       v
Deploy to matching JDK / OS / CPU runtime
~~~

### Các nguyên tắc khi đóng gói

- Đặt JAR và cache thuộc cùng build ID hoặc cùng source revision.
- Đặt tên cache có thể truy nguyên, ví dụ app-1.4.1-linux-x64-jdk25.aot.
- Tạo cache riêng cho từng OS/CPU target.
- Không tái sử dụng cache sau khi thay dependency hoặc rebuild JAR.
- Chỉ promote cache khi bước verify và benchmark đạt tiêu chí của dự án.
- Có thể triển khai ứng dụng không cache như phương án fallback nếu cache không dùng được.
- Giữ quyền ghi cache ở build stage và quyền đọc cache tối thiểu ở runtime.

Với container, đặt cache trong image hoặc mount từ artifact store theo cách bảo đảm file khớp với JAR và runtime. Tránh một volume cache dùng chung cho nhiều phiên bản ứng dụng khác nhau.

### Cache là artifact tối ưu hóa, không phải dữ liệu nghiệp vụ

AOT cache không nên chứa dữ liệu nhạy cảm của người dùng từ training workload. Dùng dữ liệu giả lập hoặc đã ẩn danh, chạy training trong môi trường cô lập và kiểm tra các đối tượng được khởi tạo trước có an toàn để tái sử dụng không. Không dùng training run để thực hiện thanh toán, gửi thông báo thật hoặc ghi dữ liệu nghiệp vụ không thể rollback.

## 16. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập A — So sánh không cache và có cache

1. Biên dịch HotPathDemo ở mục 9 bằng JDK 25.
2. Đo nhiều lần chạy không có AOT cache.
3. Tạo hotdemo.aot bằng -XX:AOTCacheOutput.
4. Chạy lại cùng JAR và tham số với -XX:AOTCache.
5. Ghi startup time, thời gian hoàn thành và độ dao động giữa các lần chạy.

**Đạt:** giải thích được sự khác biệt giữa training time và production time; không dùng một lần chạy duy nhất làm kết luận.

### Bài tập B — Training workload có đại diện không?

Tạo hai cache cho cùng ứng dụng: cache thứ nhất chỉ chạy startup/health check; cache thứ hai chạy thêm luồng tạo đơn hàng, tra cứu và nhánh khuyến mãi. So sánh cache size, hot methods và warm-up curve.

**Đạt:** giải thích được vì sao profile phụ thuộc workload và vì sao thêm mọi nhánh hiếm chưa chắc có lợi.

### Bài tập C — Kiểm tra chế độ AOT

Chạy ứng dụng với AOTMode=on để xác nhận cache được nạp. Sau đó đổi JAR hoặc dùng cache của JDK release khác trong môi trường test, quan sát lỗi. Thử auto và -Xlog:aot để xác định hành vi fallback.

**Đạt:** phân biệt fail-fast của on với fallback của auto.

### Bài tập D — Tách training và assembly

Tạo .aotconf bằng AOTMode=record, sau đó tạo .aot bằng AOTMode=create. Ghi lại tài nguyên sử dụng và so với quy trình một lệnh AOTCacheOutput.

**Đạt:** giải thích được lý do tách bước khi assembly cần thêm CPU/RAM hoặc khi cần lưu riêng configuration artifact.

### Bài tập E — Quan sát hot methods

Ghi JFR trong training run, xem jfr view hot-methods và đối chiếu với workload đã gửi. Chọn một đường nghiệp vụ chưa được gọi, thêm nó vào training rồi tạo cache mới.

**Đạt:** phân biệt JFR recording phục vụ phân tích với method profiles nội bộ mà JVM lưu vào AOT cache.

### Bài tập F — Kiểm tra tương thích nền tảng

Tạo cache trên một nền tảng, thử dùng trên JDK release hoặc kiến trúc CPU khác trong môi trường kiểm thử. Ghi nhận vì sao phải tạo cache riêng và cách pipeline gắn cache với artifact/runtime.

**Đạt:** xác định được application, JDK, OS và CPU là các yếu tố ràng buộc của cache.

### Câu hỏi tự kiểm tra

1. Method profiling trong JEP 515 khác JFR profiling như thế nào?
2. Vì sao method profiles giúp JIT tối ưu sớm hơn sau khi JVM khởi động?
3. JEP 515 có biên dịch trước toàn bộ Java methods thành native code không?
4. JEP 483, JEP 514 và JEP 515 đóng góp những phần nào vào AOT cache Java 25?
5. Vì sao training workload chỉ chạy health check có thể không cải thiện warm-up của nghiệp vụ chính?
6. -XX:AOTCacheOutput khác -XX:AOTCache như thế nào?
7. Khi nào nên tách record và create thành hai bước?
8. Vì sao AOT cache phải được tạo lại sau khi rebuild JAR hoặc nâng JDK?
9. AOTMode=auto khác AOTMode=on ở hành vi khi cache không tương thích như thế nào?
10. Vì sao không thể suy ra mức tăng tốc cố định cho mọi ứng dụng?
11. Hạn chế AOT cache với ZGC trên Java 25 được cải thiện ở phiên bản nào?
12. Cần đo những chỉ số nào để chứng minh warm-up đã tốt hơn?

## 17. Tài liệu tham khảo chính thức

- [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): method execution profiles được đưa vào AOT cache trong Java 25.
- [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): đơn giản hóa quy trình tạo AOT cache.
- [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): AOT cache và workflow training/assembly/production ban đầu trong JDK 24.
- [The java Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): các tùy chọn AOTCache, AOTCacheOutput, AOTConfiguration, AOTMode và cách chẩn đoán.
- [Performance Improvements in JDK 25 — Inside Java](https://inside.java/2025/10/20/jdk-25-performance-improvements/): giải thích tác động của JEP 515 tới JIT warm-up.
- [Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations — Inside Java](https://inside.java/2026/01/09/run-aot-cache/): hướng dẫn training workload, tạo cache, xác minh tương thích và đo hot methods.
- [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): thay đổi trong JDK 26 để AOT object caching hỗ trợ mọi GC.
- [Oracle JDK 26 Release Notes — JEP 516](https://www.oracle.com/java/technologies/javase/26all-relnotes.html): xác nhận hỗ trợ AOT cache với ZGC và các garbage collector khác trong JDK 26.

**Ghi chú tính hiện hành:** JEP 515 là tính năng Java 25 đã hoàn thiện, không phải preview. AOT method profiling vẫn hữu ích khi chạy ứng dụng trên JDK 25; tuy nhiên, cần phân biệt giới hạn AOT object caching của JDK 25 với cải tiến JEP 516 trong JDK 26. Không dùng các cờ thử nghiệm/diagnostic không được tài liệu hóa như cấu hình production mặc định.

**Kết quả cần nộp:** chương trình có hot path, AOT cache tạo từ training workload, lệnh production nạp cache, kết quả -Xlog:aot, JFR/hot-method evidence nếu dùng, bảng benchmark trước/sau và checklist tương thích artifact/JDK/OS/CPU. Qua đó, bạn chứng minh được vai trò của method profiles trong việc giúp JIT bắt đầu tối ưu sớm hơn và biết khi nào AOT cache đem lại lợi ích thực tế cho ứng dụng Java 25.
