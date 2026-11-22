# Đồ thị quan hệ trước–sau trong Spring Boot Auto Configuration: bắc cầu và vòng lặp thứ tự

## 1. Vấn đề cần giải quyết

Khi Spring Boot khởi động, nhiều **auto-configuration class** có thể tham gia đăng ký bean definition. Một class chỉ đăng ký bean khi bean do class khác cung cấp đã được xử lý trước, ví dụ dùng `@ConditionalOnBean` để phát hiện bean phụ thuộc. Vì vậy phải diễn tả **quan hệ thứ tự** giữa các auto-configuration.

Cách hiểu rõ nhất là xem chúng như **đồ thị có hướng (directed graph)**:

- Mỗi **đỉnh** là một auto-configuration, ví dụ `DataAutoConfiguration`, `RepositoryAutoConfiguration` và `ApiAutoConfiguration`.
- Cạnh **A → B** nghĩa là khi A và B được chọn, Spring Boot cần **xử lý A trước B**.
- Một chuỗi **A → B → C** có quan hệ **bắc cầu**: A cũng phải trước C.
- Chu trình **A → B → C → A** đòi một class đứng trước chính nó theo chuỗi quan hệ, không thể có thứ tự tuyến tính đáp ứng toàn bộ cạnh.

Sơ đồ minh họa:

~~~mermaid
flowchart LR
    A["DataAutoConfiguration"] --> B["RepositoryAutoConfiguration"]
    B --> C["ApiAutoConfiguration"]
~~~

**Phạm vi quan trọng:** trước/sau là **thứ tự xử lý cấu hình để đăng ký bean definition**, không phải thứ tự constructor của các bean được tạo, thứ tự gọi service, thứ tự khởi tạo database hay thứ tự chạy request. Spring Boot 3.3 mô tả rõ sự khác biệt này trong tài liệu auto-configuration.

Mục tiêu của bài là đọc đúng chiều mũi tên từ annotation, suy ra thứ tự cho một đồ thị không chu trình, nhận diện vòng lặp và sửa cách mô hình hóa phụ thuộc.

## 2. Chuyển `before` và `after` thành cạnh

Spring Boot 3.3 hỗ trợ:
- `@AutoConfiguration(before = X.class)` và `@AutoConfiguration(after = X.class)`.
- `@AutoConfiguration(beforeName = "tên.lớp")` và `@AutoConfiguration(afterName = "tên.lớp")`.
- Annotation chuyên dụng `@AutoConfigureBefore` và `@AutoConfigureAfter`.
- `@AutoConfigureOrder` cho thứ tự ưu tiên khi muốn sắp xếp các auto-configuration mà không biểu đạt một quan hệ phụ thuộc class cụ thể.

Quy ước: **mũi tên đi từ cấu hình đứng trước tới cấu hình đứng sau**.

| Khai báo | Đặt ở đâu | Quan hệ |
| --- | --- | --- |
| `@AutoConfiguration(before = B.class)` | Trên A | A → B |
| `@AutoConfiguration(after = A.class)` | Trên B | A → B |
| `@AutoConfigureBefore(B.class)` | Trên A | A → B |
| `@AutoConfigureAfter(A.class)` | Trên B | A → B |
| `@AutoConfiguration(beforeName = "com.example.BAutoConfiguration")` | Trên A | A → B nếu B tham gia |
| `@AutoConfiguration(afterName = "com.example.AAutoConfiguration")` | Trên B | A → B nếu A tham gia |

Một bên khai báo `before` hay bên kia khai báo `after` có thể cùng biểu đạt một cạnh. Không cần nhân đôi ràng buộc nếu đã mô tả đúng quan hệ.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
class DataAutoConfiguration {
}

@AutoConfiguration(after = DataAutoConfiguration.class)
class RepositoryAutoConfiguration {
}

@AutoConfiguration(after = RepositoryAutoConfiguration.class)
class ApiAutoConfiguration {
}
~~~

Ba class trên là **trích đoạn minh họa metadata**; để chạy trong ứng dụng thật cần đăng ký auto-configuration bằng cơ chế phát hiện tương ứng và có các bean cụ thể. Chúng tạo đồ thị yêu cầu:

~~~text
DataAutoConfiguration -> RepositoryAutoConfiguration
RepositoryAutoConfiguration -> ApiAutoConfiguration
~~~

Nếu đặt `@AutoConfiguration(before = RepositoryAutoConfiguration.class)` lên `DataAutoConfiguration` thì hướng Data → Repository vẫn không đổi.

### Khi nào dùng tên class dạng chuỗi?

`beforeName`/`afterName` cho phép nói đến auto-configuration ở một thư viện khác qua tên đầy đủ khi muốn tránh phụ thuộc trực tiếp tới class ấy ở compile time. Ví dụ:

~~~java
@AutoConfiguration(
    afterName = "com.vendor.integration.VendorAutoConfiguration"
)
class ExtensionAutoConfiguration {
}
~~~

Đây là một **ràng buộc tương đối**: nó không khiến `VendorAutoConfiguration` tự xuất hiện trong danh sách cấu hình được import. Nếu class mục tiêu là nested class, tên class nhị phân trong chuỗi dùng `$` để phân cách outer và nested class.

## 3. Sắp xếp tô pô (topological ordering)

Để thực thi một danh sách tuyến tính thỏa các cạnh, đồ thị phải là **DAG (directed acyclic graph)**: đồ thị có hướng và không có chu trình.

Thứ tự `v1, v2, ..., vn` là một **topological order** nếu với mọi cạnh A → B, A đứng trước B.

Ví dụ hình thoi:

~~~mermaid
flowchart LR
    A["A"] --> B["B"]
    A --> C["C"]
    B --> D["D"]
    C --> D
~~~

Các điều kiện phải thỏa: A trước B; A trước C; B trước D; C trước D. Từ đó A phải trước D.

Cả hai thứ tự đều hợp lệ:

~~~text
A, B, C, D
A, C, B, D
~~~

**Không suy ra B trước C** vì không có đường đi B → C. Hai cấu hình không có ràng buộc trước–sau là **không so sánh được trong thứ tự riêng phần**; một thứ tự được quan sát ở một lần chạy không nên được coi là hợp đồng nghiệp vụ nếu chưa khai báo mối quan hệ cần thiết.

Điều đó dẫn tới nguyên tắc: thêm cạnh để diễn tả **phụ thuộc thực**, không thêm cạnh để ép mọi class vào một chuỗi dài khi không có yêu cầu.

## 4. Quan hệ bắc cầu (transitive relationship)

Cho chuỗi:

~~~text
A -> B
B -> C
C -> D
~~~

Bằng tính bắc cầu ta suy ra:

~~~text
A -> C
B -> D
A -> D
~~~

Nếu A phải đứng trước B và B phải đứng trước C thì không cần thêm riêng `before = C.class` ở A chỉ để “nhắc lại” điều đã được đảm bảo bởi đường đi. Thay vì lưu nhiều cạnh dư thừa, có thể dùng **transitive reduction** để giữ các cạnh tối thiểu giúp đồ thị dễ đọc hơn.

Trong Spring Boot:

~~~java
@AutoConfiguration
class AAutoConfiguration {
}

@AutoConfiguration(after = AAutoConfiguration.class)
class BAutoConfiguration {
}

@AutoConfiguration(after = BAutoConfiguration.class)
class CAutoConfiguration {
}

@AutoConfiguration(after = CAutoConfiguration.class)
class DAutoConfiguration {
}
~~~

Khi A, B, C, D đều là ứng viên, chuỗi A → B → C → D buộc A trước D. Các annotation ở đây chỉ diễn tả quan hệ, không sinh thêm bean và không đặt điều kiện chọn class.

**Trường hợp cần cân nhắc:** Nếu B là cấu hình tùy chọn và bị lọc khỏi tập ứng viên, trong đồ thị của các ứng viên đang được xử lý không còn một đường đi hoàn chỉnh A → B → C. Nếu C **luôn** cần đứng sau A bất kể B có tham gia hay không, nên khai báo yêu cầu A → C một cách trực tiếp hoặc tổ chức lại trách nhiệm cấu hình. Đừng phụ thuộc duy nhất vào một đỉnh trung gian có thể vắng mặt để biểu đạt yêu cầu quan trọng.

Không cần thêm mọi cạnh bắc cầu “cho chắc”; chỉ thêm cạnh trực tiếp khi nó thể hiện một sự phụ thuộc cần giữ độc lập.

## 5. Vòng lặp thứ tự (ordering cycle)

Xét ba ràng buộc:

~~~text
A -> B
B -> C
C -> A
~~~

Đồ thị:

~~~mermaid
flowchart LR
    A["A"] --> B["B"]
    B --> C["C"]
    C --> A
~~~

Nếu chọn A trước B và B trước C, bắt buộc A trước C. Nhưng C → A lại buộc C trước A. Suy ra A phải đứng trước chính A, điều không thể xảy ra trong một thứ tự tuyến tính.

Một ví dụ nguồn tạo vòng lặp:

~~~java
@AutoConfiguration(after = CAutoConfiguration.class)
class AAutoConfiguration {
}

@AutoConfiguration(after = AAutoConfiguration.class)
class BAutoConfiguration {
}

@AutoConfiguration(after = BAutoConfiguration.class)
class CAutoConfiguration {
}
~~~

Đọc theo quy ước sẽ được C → A, A → B, B → C, tức một chu trình.

### Các dạng chu trình cần phát hiện

| Dạng | Cạnh | Biểu hiện |
| --- | --- | --- |
| Chu trình hai nút | A → B, B → A | Mỗi class đều yêu cầu đứng trước class kia |
| Chu trình ba nút | A → B, B → C, C → A | Chỉ thấy khi ghép ít nhất ba metadata |
| Chu trình dài | A → B → C → D → A | Dễ bị che khuất khi class ở nhiều thư viện |
| Cạnh tự thân | A → A | Yêu cầu class đứng trước chính nó |
| `before` và `after` mâu thuẫn | A trước B nhưng A cũng sau B | Hai cạnh ngược chiều do ghi annotation |

**Vòng lặp trước–sau không phải vòng lặp tiêm phụ thuộc bean.** Ví dụ bean A constructor-inject bean B, bean B constructor-inject bean A là bài toán circular bean dependency lúc khởi tạo. Còn ordering cycle là bài toán **metadata sắp xếp auto-configuration**. Có thể tồn tại ordering cycle dù các bean hoàn toàn không tham chiếu lẫn nhau.

Từ góc độ toán học, **không tồn tại thứ tự thỏa mọi cạnh của một chu trình**. Tuy nhiên, không nên suy đoán rằng mọi bản Spring Boot đều ném ra một exception giống nhau cho metadata này. Hành vi cụ thể của bộ sắp xếp có thể phụ thuộc implementation và phiên bản. Thiết kế đúng cần tránh chu trình thay vì dựa vào việc hệ thống chọn “thắng” một cạnh nào đó.

## 6. Vì sao thay `@Order` hoặc `@DependsOn` không sửa được chu trình?

Các cơ chế sau giải quyết bài toán **khác nhau**:

| Cơ chế | Dùng cho | Không đảm bảo |
| --- | --- | --- |
| `@AutoConfiguration(before/after)` hoặc `@AutoConfigureBefore/After` | Quan hệ tương đối giữa auto-configuration class | Thứ tự tạo instance bean |
| `@AutoConfigureOrder` | Độ ưu tiên áp dụng auto-configuration khi không muốn/không thể tham chiếu trực tiếp từng class | Không biến A < B < C < A thành một thứ tự hợp lệ |
| `@DependsOn` | Ràng buộc khởi tạo instance cho các bean đã đăng ký | Không làm một `@ConditionalOnBean` từng false thành true |
| `@Order`/`Ordered` trên các đối tượng Spring phù hợp | Thứ tự khi sắp collection, interceptor, chiến lược... theo ngữ cảnh | Không tự định nghĩa cạnh trước–sau giữa auto-configuration |
| Thứ tự dòng trong `AutoConfiguration.imports` | Khai báo các class ứng viên tự động | Không nên dùng làm hợp đồng thứ tự phụ thuộc |

Giả sử `RepositoryAutoConfiguration` chỉ đăng ký repository khi `DataSource` đã được xử lý qua `@ConditionalOnBean(DataSource.class)`. Nếu repository được xét trước cấu hình tạo data source, điều kiện có thể không khớp. Chỉ thêm `@DependsOn("dataSource")` vào một bean chưa được đăng ký **không hồi tố tạo lại bean definition**. Cần giải quyết chính thứ tự bean definition bằng quan hệ auto-configuration thích hợp.

Theo tài liệu Spring Boot 3.3, ordering metadata chỉ điều khiển **thứ tự đăng ký bean definitions**. Bean instances được tạo sau đó theo quan hệ dependency và `@DependsOn`; không dùng log constructor để kết luận trực tiếp thứ tự sắp xếp các auto-configuration.

## 7. Test Spring Boot 3.3: A → B → C và quan hệ bắc cầu

Ví dụ Java 17+ sau có thể kiểm chứng trong một dự án Spring Boot 3.3 đã khai báo `spring-boot-starter-test` (JUnit 5, AssertJ, `ApplicationContextRunner`). Các class `RootService`, `MiddleService`, `FinalService` được định nghĩa đầy đủ để tập trung vào điều kiện đăng ký bean.

Đường dẫn `src/test/java/com/example/demo/AutoConfigurationOrderingGraphTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderingGraphTest {

    static final class RootService {
        String name() {
            return "root";
        }
    }

    static final class MiddleService {
        private final RootService root;

        MiddleService(RootService root) {
            this.root = root;
        }

        String name() {
            return root.name() + "->middle";
        }
    }

    static final class FinalService {
        private final MiddleService middle;

        FinalService(MiddleService middle) {
            this.middle = middle;
        }

        String name() {
            return middle.name() + "->final";
        }
    }

    @AutoConfiguration
    static class RootAutoConfiguration {

        @Bean
        RootService rootService() {
            return new RootService();
        }
    }

    @AutoConfiguration(after = RootAutoConfiguration.class)
    static class MiddleAutoConfiguration {

        @Bean
        @ConditionalOnBean(RootService.class)
        MiddleService middleService(RootService root) {
            return new MiddleService(root);
        }
    }

    @AutoConfiguration(after = MiddleAutoConfiguration.class)
    static class FinalAutoConfiguration {

        @Bean
        @ConditionalOnBean(MiddleService.class)
        FinalService finalService(MiddleService middle) {
            return new FinalService(middle);
        }
    }

    @Test
    void transitiveOrderHoldsEvenWhenInputIsReversed() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FinalAutoConfiguration.class,
                        MiddleAutoConfiguration.class,
                        RootAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(RootService.class);
                    assertThat(context).hasSingleBean(MiddleService.class);
                    assertThat(context).hasSingleBean(FinalService.class);
                    assertThat(context.getBean(FinalService.class).name())
                            .isEqualTo("root->middle->final");
                });
    }

    @Test
    void missingRootDoesNotCreateDownstreamBeans() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        FinalAutoConfiguration.class,
                        MiddleAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(RootService.class);
                    assertThat(context).doesNotHaveBean(MiddleService.class);
                    assertThat(context).doesNotHaveBean(FinalService.class);
                });
    }
}
~~~

Diễn giải:
- Cạnh **Root → Middle** đến từ `MiddleAutoConfiguration(after = RootAutoConfiguration.class)`.
- Cạnh **Middle → Final** đến từ `FinalAutoConfiguration(after = MiddleAutoConfiguration.class)`.
- Vì hai ràng buộc đó, **Root → Final** là quan hệ bắc cầu.
- Khi đủ các ứng viên, root được đăng ký trước khi đánh giá condition của middle; middle được đăng ký trước khi đánh giá condition của final.
- Khi root không tham gia, `after = RootAutoConfiguration.class` không tự import root. `@ConditionalOnBean(RootService.class)` tại middle không khớp, nên final cũng không nhận được `MiddleService`.

Lệnh chạy trong dự án có Gradle wrapper và dependency test:

~~~bash
./gradlew test --tests "com.example.demo.AutoConfigurationOrderingGraphTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.AutoConfigurationOrderingGraphTest"
~~~

**Kết quả mong đợi:** hai test PASS. Test sử dụng assertion trên bean thực được đăng ký và chuỗi `root->middle->final`, không yêu cầu một dòng stdout nhất định của Gradle. Chuỗi này là kết quả của các phương thức `name()` trong ví dụ, **không phải trace thứ tự gọi constructor**.

`AutoConfigurations.of(...)` đưa các auto-configuration vào fixture test trực tiếp; ứng dụng thực đóng gói starter cần liệt kê class trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` để Spring Boot tự phát hiện.

## 8. Chương trình Java 17 độc lập: kiểm tra DAG và phát hiện cycle

Để thấy rõ nguyên lý của đồ thị, thuật toán Kahn có thể kiểm tra xem có một thứ tự topo hay không:

1. Đếm **in-degree** (số cạnh đi vào) từng đỉnh.
2. Đưa các đỉnh có in-degree bằng 0 vào hàng đợi.
3. Lấy một đỉnh ra, đưa vào kết quả, xóa ảnh hưởng các cạnh đi ra bằng cách giảm in-degree.
4. Nếu không xử lý được toàn bộ đỉnh thì có chu trình và không thể tạo topological ordering đầy đủ.

Tạo file `AutoConfigurationGraphDemo.java` (chỉ cần JDK 17+, **không cần Spring**):

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;

public class AutoConfigurationGraphDemo {

    record Edge(String from, String to) {
    }

    static List<String> order(List<String> nodes, List<Edge> edges) {
        Map<String, Integer> incoming = new HashMap<>();
        Map<String, List<String>> outgoing = new HashMap<>();

        for (String node : nodes) {
            if (incoming.putIfAbsent(node, 0) != null) {
                throw new IllegalArgumentException("Duplicate node");
            }
            outgoing.put(node, new ArrayList<>());
        }

        for (Edge edge : edges) {
            if (!incoming.containsKey(edge.from())
                    || !incoming.containsKey(edge.to())) {
                throw new IllegalArgumentException("Unknown node");
            }
            outgoing.get(edge.from()).add(edge.to());
            incoming.merge(edge.to(), 1, Integer::sum);
        }

        PriorityQueue<String> ready = new PriorityQueue<>();
        for (String node : nodes) {
            if (incoming.get(node) == 0) {
                ready.add(node);
            }
        }

        List<String> sorted = new ArrayList<>();
        while (!ready.isEmpty()) {
            String current = ready.remove();
            sorted.add(current);
            for (String next : outgoing.get(current)) {
                int count = incoming.merge(next, -1, Integer::sum);
                if (count == 0) {
                    ready.add(next);
                }
            }
        }

        if (sorted.size() != nodes.size()) {
            throw new IllegalArgumentException("Graph has a cycle");
        }
        return sorted;
    }

    public static void main(String[] args) {
        List<Edge> acyclic = List.of(
                new Edge("A", "B"),
                new Edge("B", "C"),
                new Edge("A", "D")
        );
        System.out.println("DAG: "
                + order(List.of("A", "B", "C", "D"), acyclic));

        List<Edge> cyclic = List.of(
                new Edge("A", "B"),
                new Edge("B", "C"),
                new Edge("C", "A")
        );
        try {
            order(List.of("A", "B", "C"), cyclic);
        } catch (IllegalArgumentException ex) {
            System.out.println("CYCLE: " + ex.getMessage());
        }
    }
}
~~~

Lệnh:

~~~bash
javac AutoConfigurationGraphDemo.java
java AutoConfigurationGraphDemo
~~~

Stdout chính xác:

~~~text
DAG: [A, B, C, D]
CYCLE: Graph has a cycle
~~~

Với DAG, hàng đợi ưu tiên chọn tên theo thứ tự alphabet; đó là cách **chương trình minh họa** chọn giữa các thứ tự topo hợp lệ. Không suy luận rằng Spring Boot dùng đúng thuật toán Kahn hoặc chính tiêu chí tie-break này. Đoạn Java chỉ minh họa rằng đồ thị không chu trình cho phép xử lý hết đỉnh, còn chu trình thì không.

## 9. Gỡ chu trình và giữ nguồn cấu hình dễ bảo trì

Khi gặp A → B → C → A:

1. **Chuyển tất cả annotation thành cạnh có hướng** và ghi nguồn: class nào, file nào, đặt `before` hay `after` tới class nào.
2. **Xác định lý do của từng cạnh.** Ví dụ B có `@ConditionalOnBean` cần bean từ A thì ràng buộc đúng là A → B; đừng đảo thành B → A.
3. **Xem các đỉnh nào thật sự là ứng viên.** Class có thể không được chọn vì không có trong imports, do bị loại trừ hoặc bị filter bằng condition. Chỉ dựa vào class trên classpath chưa đủ.
4. **Loại quan hệ không cần thiết hoặc bị khai báo sai.** Nếu C không cần chờ B, cạnh B → C có thể là metadata thừa. Chỉ bỏ sau khi xác minh nhu cầu thực.
5. **Tách một phần hạ tầng chung ra cấu hình nền tảng.** Ví dụ nếu A và C cần dùng lẫn nhau, cân nhắc cấu hình D tạo phần dùng chung trước, rồi cả A và C phụ thuộc D theo một chiều; không tạo vòng.
6. **Kiểm thử cả trường hợp đầy đủ lẫn thiếu một đỉnh.** Các condition phải khớp khi prerequisite có mặt và phải back off đúng lúc khi không có.

Một ví dụ sửa hướng:

~~~text
Trước: A -> B -> C -> A     (mâu thuẫn)
Sau:   A -> B -> C          (có thể sắp xếp)
~~~

Đây chỉ là **đồ thị minh họa**; cạnh nào thực tế được phép xóa phụ thuộc vào nhu cầu đăng ký bean của từng class. Không tùy tiện phá vòng bằng cách xóa cạnh khi điều đó làm sai nghiệp vụ.

Nếu cần bậc ưu tiên toàn cục giữa các auto-configuration không biết nhau, có thể xem `@AutoConfigureOrder`, nhưng nó không thay thế việc mô tả và gỡ một phụ thuộc vòng. Không coi kết quả khởi động thành công ở một phiên bản là bằng chứng tất cả các cạnh mâu thuẫn đã được thực thi.

## 10. Chẩn đoán các trường hợp bean không được đăng ký

Hiện tượng điển hình: auto-configuration B có `@ConditionalOnBean(RootService.class)` nhưng bean B không xuất hiện, dù source code có auto-configuration A định nghĩa `RootService`.

Cách điều tra:
- Xác nhận A thực sự là **auto-configuration ứng viên**, và bean `RootService` không bị điều kiện khác loại bỏ.
- Đọc metadata `before/after` của A và B, xác nhận cạnh **A → B**. Bean conditions thường chỉ xét những bean definitions đã được xử lý đến thời điểm đánh giá.
- Xác nhận kiểu trả về của method `@Bean` đủ cụ thể để Spring biết kiểu bean mà chưa tạo instance.
- Dùng `ApplicationContextRunner` để dựng context với A và B, kiểm tra cả nhánh có/không có prerequisite. Thử cấu hình đầu vào theo thứ tự ngược để xác minh metadata hoạt động.
- Bật `debug=true` hoặc `--debug` để xem **Condition Evaluation Report** của Spring Boot và lý do match/no-match. Nếu ứng dụng expose Actuator endpoint `/actuator/conditions` phù hợp, có thể xem báo cáo điều kiện tại đó.
- Nếu thấy thiếu bean, đừng tự động kết luận lỗi vòng lặp order: có thể class không được import, property không đúng, type metadata chưa thấy, hoặc bean bị thiếu do condition khác.

Tránh khắc phục chỉ bằng việc đổi vị trí các dòng trong imports hoặc chỉ thêm `@DependsOn` vào consumer. Hai thao tác đó không diễn tả chính xác nhu cầu xử lý auto-configuration trước–sau.

## 11. Lỗi tư duy thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “A đứng trước B nghĩa là instance bean A luôn tạo trước instance bean B.” | Chỉ bảo đảm thứ tự **đăng ký bean definition** khi metadata được thỏa; tạo instance theo dependency/lifecycle. |
| “A → B và B → C cần khai báo thêm A → C để tính bắc cầu có hiệu lực.” | Không; A trước C được suy ra khi đường đi áp dụng. |
| “A → B, A → C suy ra B → C.” | Không; B và C không có quan hệ với nhau. |
| “A → B → C → A vẫn có thể chọn thứ tự phù hợp nếu cấu hình chạy đủ nhanh.” | Không tồn tại thứ tự tuyến tính thỏa toàn bộ chu trình. |
| “Mọi ordering cycle chắc chắn ném cùng một exception Spring Boot.” | Không nên dựa vào một phản ứng implementation cụ thể; sửa metadata mâu thuẫn. |
| “`@DependsOn` và `@AutoConfigureAfter` giống nhau.” | Một bên điều khiển tạo instance; một bên điều khiển thứ tự áp dụng auto-configuration. |
| “`afterName` tự import class được nêu.” | Nó là metadata quan hệ nếu class mục tiêu tham gia; không tự chọn class đó. |
| “Đã có class `RootService` trên classpath thì `@ConditionalOnBean` luôn khớp.” | Phải có **bean definition phù hợp** được nhìn thấy khi condition được đánh giá. |
| “Thứ tự thấy trong imports là contract của application.” | Hãy dùng metadata before/after cho quan hệ cần ổn định. |

## 12. Bài tập tự đánh giá

1. Trên B có `@AutoConfiguration(after = A.class)`. Cạnh nào xuất hiện? **A → B**.
2. Trên A có `@AutoConfiguration(before = B.class)`. Nó mâu thuẫn với câu 1 không? **Không**; cũng là A → B.
3. A → B → C → D buộc A trước D không? **Có**, theo quan hệ bắc cầu khi các đỉnh tham gia.
4. Hình thoi A → B, A → C, B → D, C → D cho phép thứ tự A,C,B,D không? **Có**.
5. Có thể sắp topo cho A → B, B → C, C → A không? **Không**.
6. Thêm `@AutoConfigureOrder(0)` có chứng minh mọi cạnh của một chu trình đều đúng không? **Không**.
7. Vì sao `@DependsOn` không giúp điều kiện `@ConditionalOnBean` từng fail được xét lại? Vì nó tác động tới **thứ tự tạo bean đã được đăng ký**, không hồi tố quá trình đánh giá điều kiện.
8. C đã phụ thuộc B, B đã phụ thuộc A, nhưng B có thể bị loại. C lại luôn cần A. Nên làm gì? **Xét tập ứng viên thực tế và khai báo trực tiếp A → C nếu đó là yêu cầu cần giữ độc lập.**
9. Tại sao chỉ thấy hai class A và B trong code chưa đủ kết luận chúng chạy theo cạnh A → B? Vì phải xác nhận cả hai **là ứng viên được áp dụng** trong runtime và ràng buộc thuộc metadata auto-configuration.
10. Làm sao xác nhận tác dụng của ordering? **Dùng `ApplicationContextRunner` kiểm tra điều kiện, bean definitions và các trường hợp đủ/thiếu prerequisite**, kết hợp báo cáo điều kiện khi cần.

## Tài liệu tham khảo

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): quan hệ `before`/`after`, imports, `@AutoConfigureOrder` và test auto-configuration.
- [Spring Boot 3.3 — `@AutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): các thuộc tính `before`, `after`, `beforeName`, `afterName`.
- [Spring Boot 3.3 — `@AutoConfigureBefore` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html): định nghĩa áp dụng cấu hình trước class khác.
- [Spring Boot 3.3 — `@AutoConfigureAfter` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html): định nghĩa áp dụng sau class khác; khác biệt với thời điểm khởi tạo bean.
