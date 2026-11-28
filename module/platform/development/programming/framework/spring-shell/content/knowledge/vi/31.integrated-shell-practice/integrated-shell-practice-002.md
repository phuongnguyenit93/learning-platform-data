# Xây nhóm lệnh quản lý tài nguyên dùng chung service

Trong bài thực hành này, chúng ta xây một CLI nhỏ để quản lý tài nguyên dùng chung trong một nhóm. Người vận hành có thể tạo tài nguyên, liệt kê theo trạng thái, xem chi tiết, bàn giao, thu hồi, thanh lý và xóa tài nguyên. Các command được chia thành nhiều lớp Spring Shell nhưng cùng sử dụng một service nghiệp vụ.

Mục tiêu quan trọng của bài không nằm ở từng command riêng lẻ. Ta cần bảo đảm tất cả command cùng đọc và cập nhật một nguồn dữ liệu, áp dụng cùng quy tắc nghiệp vụ và không tạo bản sao trạng thái trong từng lớp command.

Ứng dụng dùng Spring Boot 4 và Spring Shell 4.0.4, mô hình đăng ký command bằng annotation. Dữ liệu được lưu trong bộ nhớ để tập trung vào cách tổ chức command và service; khi khởi động lại ứng dụng, dữ liệu mẫu sẽ mất. Phần cuối chỉ ra cách thay service bằng repository hoặc database khi triển khai thực tế.

## 1. Kết quả cần đạt

Nhóm command có prefix là **resource**:

| Command | Mục đích | Thay đổi dữ liệu |
|---|---|---|
| **resource add** | Tạo tài nguyên mới | Thêm tài nguyên trạng thái AVAILABLE |
| **resource list** | Liệt kê tài nguyên, có thể lọc trạng thái | Không |
| **resource show** | Xem chi tiết theo mã | Không |
| **resource assign** | Bàn giao tài nguyên | Chuyển sang IN_USE |
| **resource release** | Thu hồi tài nguyên | Chuyển về AVAILABLE |
| **resource retire** | Thanh lý tài nguyên | Chuyển sang RETIRED |
| **resource delete** | Xóa tài nguyên | Xóa khỏi danh mục nếu không đang được sử dụng |

Một tài nguyên có mã tự sinh, tên, nhóm phân loại, trạng thái và thời điểm tạo. Service áp dụng các quy tắc:

- Tên và nhóm phân loại không được để trống.
- Tên tài nguyên tối đa 80 ký tự; nhóm phân loại tối đa 40 ký tự.
- Mỗi tài nguyên có một mã duy nhất.
- Tài nguyên đang IN_USE không được xóa.
- Tài nguyên đang IN_USE phải được release trước khi retire.
- Tài nguyên đã RETIRED không được assign hoặc release trở lại.

Sau khi hoàn thành, các command ở ba lớp khác nhau vẫn thao tác trên cùng một ResourceCatalogService singleton do Spring quản lý.

## 2. Tổ chức source code

Có thể đặt các lớp trong cùng package của ứng dụng:

~~~text
src/main/java/com/example/resourcecli/
├── ResourceCliApplication.java
├── domain/
│   ├── ResourceItem.java
│   └── ResourceStatus.java
├── service/
│   └── ResourceCatalogService.java
└── shell/
    ├── ResourceWriteCommands.java
    ├── ResourceQueryCommands.java
    ├── ResourceLifecycleCommands.java
    └── ResourceOutput.java
~~~

Các command chỉ nhận input, gọi service và trình bày kết quả. Quy tắc kiểm tra dữ liệu và thay đổi trạng thái nằm trong service. Domain model mô tả tài nguyên và trạng thái hợp lệ.

Không giữ một Map riêng trong từng command class. Nếu mỗi lớp command tự lưu dữ liệu, lệnh add có thể ghi vào một danh sách trong khi list đọc từ một danh sách khác. Tiêm cùng một service qua constructor giúp Spring cung cấp cùng bean cho mọi command.

## 3. Tạo domain model

Đầu tiên khai báo các trạng thái:

~~~java
package com.example.resourcecli.domain;

public enum ResourceStatus {
    AVAILABLE,
    IN_USE,
    RETIRED
}
~~~

Một tài nguyên được biểu diễn bằng record bất biến:

~~~java
package com.example.resourcecli.domain;

import java.time.Instant;

public record ResourceItem(
        String id,
        String name,
        String category,
        ResourceStatus status,
        Instant createdAt) {

    public ResourceItem withStatus(ResourceStatus nextStatus) {
        return new ResourceItem(
                id,
                name,
                category,
                nextStatus,
                createdAt
        );
    }
}
~~~

Record giúp dữ liệu sau khi tạo không bị thay đổi trực tiếp. Khi chuyển trạng thái, method withStatus tạo một record mới và giữ nguyên mã, tên, nhóm phân loại cùng thời điểm tạo.

Không đưa logic đọc terminal, in bảng hoặc parse command line vào domain model. Domain chỉ mô tả dữ liệu và những phép biến đổi thuộc về tài nguyên.

## 4. Xây ResourceCatalogService dùng chung

Service là nơi duy nhất sở hữu danh mục tài nguyên. Trong ví dụ này, ConcurrentHashMap lưu dữ liệu theo mã; AtomicLong tạo mã tăng dần. Các thao tác thay đổi trạng thái sử dụng compute để kiểm tra và cập nhật một mục nguyên tử.

~~~java
package com.example.resourcecli.service;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.stereotype.Service;

import com.example.resourcecli.domain.ResourceItem;
import com.example.resourcecli.domain.ResourceStatus;

@Service
public class ResourceCatalogService {

    private final ConcurrentMap<String, ResourceItem> resources =
            new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong();

    public ResourceItem add(String name, String category) {
        String normalizedName = requireText(name, "Tên", 80);
        String normalizedCategory = requireText(category, "Nhóm", 40);
        String id = String.format(
                Locale.ROOT,
                "R-%04d",
                sequence.incrementAndGet()
        );

        ResourceItem item = new ResourceItem(
                id,
                normalizedName,
                normalizedCategory,
                ResourceStatus.AVAILABLE,
                Instant.now()
        );

        resources.put(id, item);
        return item;
    }

    public List<ResourceItem> list(ResourceStatus status) {
        return resources.values().stream()
                .filter(item -> status == null || item.status() == status)
                .sorted(Comparator.comparing(ResourceItem::id))
                .toList();
    }

    public Optional<ResourceItem> findById(String id) {
        String key = requireText(id, "Mã tài nguyên", 20);
        return Optional.ofNullable(resources.get(key));
    }

    public Optional<ResourceItem> changeStatus(
            String id,
            ResourceStatus nextStatus) {

        String key = requireText(id, "Mã tài nguyên", 20);
        if (nextStatus == null) {
            throw new IllegalArgumentException("Trạng thái mới không được để trống.");
        }

        AtomicReference<ResourceItem> changed = new AtomicReference<>();
        resources.compute(key, (ignored, current) -> {
            if (current == null) {
                return null;
            }
            if (current.status() == ResourceStatus.RETIRED) {
                throw new IllegalStateException(
                        "Tài nguyên đã thanh lý, không thể đổi trạng thái."
                );
            }
            if (current.status() == ResourceStatus.IN_USE
                    && nextStatus == ResourceStatus.RETIRED) {
                throw new IllegalStateException(
                        "Hãy thu hồi tài nguyên trước khi thanh lý."
                );
            }

            ResourceItem updated = current.withStatus(nextStatus);
            changed.set(updated);
            return updated;
        });

        return Optional.ofNullable(changed.get());
    }

    public boolean delete(String id) {
        String key = requireText(id, "Mã tài nguyên", 20);
        AtomicBoolean removed = new AtomicBoolean();

        resources.compute(key, (ignored, current) -> {
            if (current == null) {
                return null;
            }
            if (current.status() == ResourceStatus.IN_USE) {
                throw new IllegalStateException(
                        "Không thể xóa tài nguyên đang được sử dụng."
                );
            }

            removed.set(true);
            return null;
        });

        return removed.get();
    }

    private String requireText(String value, String label, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + " không được để trống.");
        }

        String normalized = value.trim();
        if (normalized.length() > maxLength) {
            throw new IllegalArgumentException(
                    label + " không được vượt quá " + maxLength + " ký tự."
            );
        }
        return normalized;
    }
}
~~~

Các method của service có hợp đồng rõ ràng:

| Method | Kết quả |
|---|---|
| **add(name, category)** | Tạo và trả về ResourceItem mới |
| **list(status)** | Trả danh sách đã sắp xếp; status null nghĩa là lấy tất cả |
| **findById(id)** | Trả Optional để phân biệt tìm thấy và không tìm thấy |
| **changeStatus(id, nextStatus)** | Trả Optional rỗng nếu không có mã; từ chối chuyển trạng thái vi phạm quy tắc |
| **delete(id)** | Trả false nếu không có mã; từ chối xóa tài nguyên đang IN_USE |

Service chuẩn hóa khoảng trắng ở đầu và cuối, kiểm tra độ dài và không phụ thuộc Spring Shell. Nhờ vậy, cùng quy tắc có thể được dùng từ command, REST API, scheduler hoặc test.

ConcurrentHashMap và các phép compute giúp thao tác trên một mã được kiểm tra/cập nhật nhất quán khi có nhiều lời gọi đồng thời. Đây vẫn là kho dữ liệu trong bộ nhớ của một process, không cung cấp persistence hoặc đồng bộ giữa nhiều instance.

## 5. Tạo lớp định dạng output dùng chung

Command không nên tự định dạng cùng một tài nguyên theo nhiều kiểu khác nhau. Tạo một helper nhỏ để các command dùng chung:

~~~java
package com.example.resourcecli.shell;

import com.example.resourcecli.domain.ResourceItem;

public final class ResourceOutput {

    private ResourceOutput() {
    }

    public static String line(ResourceItem item) {
        return "%s | %s | %s | %s".formatted(
                item.id(),
                item.name(),
                item.category(),
                item.status()
        );
    }
}
~~~

Helper này chỉ định dạng dữ liệu cho terminal. Nó không truy cập danh mục hoặc thay đổi trạng thái.

## 6. Tạo command thêm và bàn giao tài nguyên

Nhóm lệnh ghi sử dụng prefix **resource**. Spring Shell 4 có **@CommandGroup** để đặt prefix và tên nhóm cho các command method trong class. Annotation này cũng đăng ký class như một Spring component.

~~~java
package com.example.resourcecli.shell;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.Option;

import com.example.resourcecli.domain.ResourceItem;
import com.example.resourcecli.domain.ResourceStatus;
import com.example.resourcecli.service.ResourceCatalogService;

@CommandGroup(
        prefix = "resource",
        name = "Quản lý tài nguyên"
)
public class ResourceWriteCommands {

    private final ResourceCatalogService catalog;

    public ResourceWriteCommands(ResourceCatalogService catalog) {
        this.catalog = catalog;
    }

    @Command(name = "add", description = "Tạo tài nguyên mới.")
    public String add(
            @Option(longName = "name", required = true) String name,
            @Option(longName = "category", required = true) String category) {

        ResourceItem item = catalog.add(name, category);
        return "Đã tạo tài nguyên: " + ResourceOutput.line(item);
    }

    @Command(name = "assign", description = "Bàn giao tài nguyên.")
    public String assign(
            @Option(longName = "id", required = true) String id) {

        return catalog.changeStatus(id, ResourceStatus.IN_USE)
                .map(item -> "Đã bàn giao tài nguyên " + item.id())
                .orElse("Không tìm thấy tài nguyên " + id + ".");
    }
}
~~~

Điểm cần chú ý:

- Class không tự tạo ResourceCatalogService bằng new. Constructor nhận bean do Spring quản lý.
- Method add chỉ kiểm tra input ở mức cú pháp qua required; quy tắc độ dài và chuẩn hóa nằm trong service.
- Method assign không trực tiếp truy cập Map. Nó gọi changeStatus và xử lý Optional.
- Tên command hoàn chỉnh được tạo từ prefix resource và tên method-level add hoặc assign.

## 7. Tạo command truy vấn dùng cùng service

Lớp truy vấn cũng nhận chính ResourceCatalogService qua constructor:

~~~java
package com.example.resourcecli.shell;

import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.Option;

import com.example.resourcecli.domain.ResourceItem;
import com.example.resourcecli.domain.ResourceStatus;
import com.example.resourcecli.service.ResourceCatalogService;

@CommandGroup(
        prefix = "resource",
        name = "Quản lý tài nguyên"
)
public class ResourceQueryCommands {

    private final ResourceCatalogService catalog;

    public ResourceQueryCommands(ResourceCatalogService catalog) {
        this.catalog = catalog;
    }

    @Command(name = "list", description = "Liệt kê tài nguyên.")
    public String list(
            @Option(longName = "status") ResourceStatus status) {

        List<ResourceItem> items = catalog.list(status);
        if (items.isEmpty()) {
            return "Không có tài nguyên phù hợp.";
        }

        return Stream.concat(
                Stream.of("MÃ | TÊN | NHÓM | TRẠNG THÁI"),
                items.stream().map(ResourceOutput::line)
        ).collect(Collectors.joining(System.lineSeparator()));
    }

    @Command(name = "show", description = "Xem chi tiết tài nguyên.")
    public String show(
            @Option(longName = "id", required = true) String id) {

        return catalog.findById(id)
                .map(ResourceOutput::line)
                .orElse("Không tìm thấy tài nguyên " + id + ".");
    }
}
~~~

Option status là tùy chọn. Khi người dùng không truyền, Spring bind null và service trả toàn bộ tài nguyên. Khi truyền một giá trị enum hợp lệ, service lọc theo trạng thái đó.

Các lời gọi:

~~~text
resource list
resource list --status=AVAILABLE
resource list --status IN_USE
resource show --id=R-0001
~~~

Nếu giá trị trạng thái không chuyển được sang ResourceStatus, parser/conversion báo lỗi trước khi command gọi service. Không cần tự tách chuỗi command line trong method.

## 8. Tạo command thu hồi, thanh lý và xóa

Nhóm lifecycle chịu trách nhiệm kết thúc vòng đời tài nguyên:

~~~java
package com.example.resourcecli.shell;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.CommandGroup;
import org.springframework.shell.core.command.annotation.Option;

import com.example.resourcecli.domain.ResourceStatus;
import com.example.resourcecli.service.ResourceCatalogService;

@CommandGroup(
        prefix = "resource",
        name = "Quản lý tài nguyên"
)
public class ResourceLifecycleCommands {

    private final ResourceCatalogService catalog;

    public ResourceLifecycleCommands(ResourceCatalogService catalog) {
        this.catalog = catalog;
    }

    @Command(name = "release", description = "Thu hồi tài nguyên đã bàn giao.")
    public String release(
            @Option(longName = "id", required = true) String id) {

        return catalog.changeStatus(id, ResourceStatus.AVAILABLE)
                .map(item -> "Đã thu hồi tài nguyên " + item.id())
                .orElse("Không tìm thấy tài nguyên " + id + ".");
    }

    @Command(name = "retire", description = "Thanh lý tài nguyên.")
    public String retire(
            @Option(longName = "id", required = true) String id) {

        return catalog.changeStatus(id, ResourceStatus.RETIRED)
                .map(item -> "Đã thanh lý tài nguyên " + item.id())
                .orElse("Không tìm thấy tài nguyên " + id + ".");
    }

    @Command(name = "delete", description = "Xóa tài nguyên khỏi danh mục.")
    public String delete(
            @Option(longName = "id", required = true) String id) {

        return catalog.delete(id)
                ? "Đã xóa tài nguyên " + id + "."
                : "Không tìm thấy tài nguyên " + id + ".";
    }
}
~~~

Ba lớp command cùng inject một kiểu service. Trong một Spring application context, mặc định một bean @Service là singleton. Vì vậy, các command thao tác trên cùng một danh mục.

Service kiểm tra quy tắc cuối cùng. Nếu một command khác trong tương lai cũng gọi changeStatus hoặc delete, quy tắc vẫn được áp dụng. Không đặt kiểm tra chỉ trong method retire hoặc delete vì đường gọi khác có thể bỏ qua chúng.

## 9. Khởi động ứng dụng và đăng ký command

Với Spring Boot, command annotation được tự động scan khi ứng dụng dùng cấu hình Spring Shell Boot phù hợp. Class chứa các command phải nằm trong phạm vi component scan của application class.

~~~java
package com.example.resourcecli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceCliApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceCliApplication.class, args);
    }
}
~~~

Đặt application class ở package cha của domain, service và shell. Khi đó component scan có thể tìm ResourceCatalogService và các class có @CommandGroup.

Trong ứng dụng Spring Boot, không cần thêm @EnableCommand chỉ để đăng ký các command annotation. Nếu dùng Spring Framework mà không có Spring Boot auto-configuration, cần cấu hình đăng ký command theo cách tương ứng với ứng dụng đó.

## 10. Chạy thử toàn bộ luồng nghiệp vụ

Khởi động ứng dụng ở interactive mode rồi thực hiện các lệnh theo thứ tự:

~~~text
help
resource add --name="Laptop phòng họp" --category=IT
resource add --name="Máy chiếu tầng 2" --category=AV
resource list
resource show --id=R-0001
resource assign --id=R-0001
resource list --status=IN_USE
resource release --id=R-0001
resource retire --id=R-0002
resource list
resource delete --id=R-0001
resource show --id=R-0001
~~~

Kết quả mong đợi:

1. Hai tài nguyên được tạo với mã R-0001 và R-0002.
2. resource list hiển thị cả hai tài nguyên ở trạng thái AVAILABLE.
3. resource show tìm được tài nguyên R-0001.
4. resource assign chuyển R-0001 sang IN_USE.
5. resource list --status=IN_USE chỉ hiển thị R-0001.
6. resource release đưa R-0001 về AVAILABLE.
7. resource retire chuyển R-0002 sang RETIRED.
8. resource delete xóa R-0001.
9. resource show --id=R-0001 báo không tìm thấy.

Luồng này chứng minh dữ liệu được chia sẻ qua các command class. Nếu service bị tạo mới trong mỗi command, lệnh list hoặc show có thể không nhìn thấy dữ liệu do add tạo ra.

## 11. Kiểm tra các quy tắc nghiệp vụ

Thử các thao tác không hợp lệ:

~~~text
resource add --name=" " --category=IT
resource add --name="Tên tài nguyên vượt quá giới hạn..." --category=IT
resource delete --id=R-0001
resource retire --id=R-0001
resource assign --id=R-9999
~~~

Điều cần xác nhận:

- Tên rỗng hoặc chỉ có khoảng trắng bị service từ chối.
- Tên vượt quá 80 ký tự bị từ chối.
- Không xóa được tài nguyên đang IN_USE.
- Không thanh lý tài nguyên đang IN_USE trước khi release.
- Mã không tồn tại không làm ứng dụng lỗi ngoài dự kiến.

Sau khi release một tài nguyên, có thể retire hoặc delete tùy chính sách. Một tài nguyên RETIRED không thể được assign lại.

## 12. Kiểm thử service độc lập

Service không phụ thuộc parser hoặc terminal, nên có thể kiểm thử bằng JUnit:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import com.example.resourcecli.domain.ResourceStatus;
import com.example.resourcecli.service.ResourceCatalogService;

class ResourceCatalogServiceTests {

    private ResourceCatalogService catalog;

    @BeforeEach
    void setUp() {
        catalog = new ResourceCatalogService();
    }

    @Test
    void createsAndFindsResource() {
        var created = catalog.add("Laptop", "IT");

        assertThat(catalog.findById(created.id()))
                .contains(created);
        assertThat(created.status()).isEqualTo(ResourceStatus.AVAILABLE);
    }

    @Test
    void doesNotDeleteResourceInUse() {
        var created = catalog.add("Projector", "AV");
        catalog.changeStatus(created.id(), ResourceStatus.IN_USE);

        assertThatThrownBy(() -> catalog.delete(created.id()))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("đang được sử dụng");
    }

    @Test
    void filtersByStatus() {
        catalog.add("Laptop", "IT");
        var projector = catalog.add("Projector", "AV");
        catalog.changeStatus(projector.id(), ResourceStatus.IN_USE);

        assertThat(catalog.list(ResourceStatus.IN_USE))
                .extracting(item -> item.id())
                .containsExactly(projector.id());
    }
}
~~~

Mỗi test tạo service mới để không phụ thuộc thứ tự thực thi test khác. Các test tập trung vào validation, trạng thái ban đầu, lọc danh sách và quy tắc không xóa tài nguyên đang sử dụng.

## 13. Kiểm thử xuyên nhiều command bằng ShellTestClient

Service test chưa chứng minh các command annotation được scan đúng hoặc mọi command đều inject cùng service. Dùng **@ShellTest** và **ShellTestClient** để gửi nhiều command trong cùng test context:

~~~java
package com.example.resourcecli;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.ContextConfiguration;
import org.springframework.shell.test.ShellAssertions;
import org.springframework.shell.test.ShellTestClient;
import org.springframework.shell.test.autoconfigure.ShellTest;

@ShellTest
@ContextConfiguration(classes = ResourceCliApplication.class)
class ResourceCommandsTests {

    @Autowired
    ShellTestClient client;

    @Test
    void commandsShareTheSameResourceCatalog() throws Exception {
        var created = client.sendCommand(
                "resource add --name=\"Laptop phòng họp\" --category=IT"
        );
        ShellAssertions.assertThat(created)
                .containsText("R-0001");

        var listed = client.sendCommand("resource list");
        ShellAssertions.assertThat(listed)
                .containsText("Laptop phòng họp");

        var assigned = client.sendCommand(
                "resource assign --id=R-0001"
        );
        ShellAssertions.assertThat(assigned)
                .containsText("Đã bàn giao");

        var filtered = client.sendCommand(
                "resource list --status=IN_USE"
        );
        ShellAssertions.assertThat(filtered)
                .containsText("R-0001")
                .containsText("IN_USE");

        var released = client.sendCommand(
                "resource release --id=R-0001"
        );
        ShellAssertions.assertThat(released)
                .containsText("Đã thu hồi");
    }
}
~~~

Test gửi command add qua một command class, list qua command class khác, assign qua lớp ghi và release qua lớp lifecycle. Việc command sau nhìn thấy thay đổi của command trước là bằng chứng các lớp cùng sử dụng một ResourceCatalogService trong context.

Nếu dùng Spring Shell test support, thêm module test tương ứng với phiên bản Spring Shell 4 đang dùng vào test runtime. @ShellTest tạo môi trường test cho shell; @ContextConfiguration cung cấp application class và component scan.

## 14. Những điều cần giữ ở service, không đặt trong command

Command là adapter giữa cú pháp CLI và nghiệp vụ. Nó nên ngắn, dễ đọc và không chứa quy tắc dữ liệu lặp lại.

| Trách nhiệm | Nơi phù hợp |
|---|---|
| Tên command, alias, mô tả và option | Command annotation |
| Chuyển input CLI thành lời gọi nghiệp vụ | Command method |
| Kiểm tra tên, category và độ dài | ResourceCatalogService |
| Sinh mã tài nguyên | ResourceCatalogService |
| Quy tắc trạng thái và quyền xóa | ResourceCatalogService |
| Tìm kiếm, lọc và sắp xếp dữ liệu | ResourceCatalogService |
| Định dạng một dòng hiển thị | ResourceOutput |
| Lưu dữ liệu bền vững | Repository/database ở tầng persistence |

Nếu sau này thêm REST controller, scheduler hoặc giao diện web, các adapter đó cũng gọi ResourceCatalogService. Không copy validation hoặc quy tắc trạng thái sang từng adapter.

## 15. Thay kho trong bộ nhớ bằng repository

Ví dụ hiện tại mất dữ liệu khi process dừng. Khi cần persistence, giữ nguyên command và hợp đồng service nhưng thay cấu trúc lưu trữ bằng repository:

~~~java
public interface ResourceRepository {

    ResourceItem save(ResourceItem item);

    List<ResourceItem> findAll();

    Optional<ResourceItem> findById(String id);

    void deleteById(String id);
}
~~~

Service sẽ inject ResourceRepository thay vì tự sở hữu ConcurrentHashMap. Quy tắc validation, chuyển trạng thái và kiểm tra không xóa tài nguyên đang dùng vẫn ở service. Repository chịu trách nhiệm lưu/đọc dữ liệu.

Với database thật, các thao tác thay đổi trạng thái và xóa cần transaction để bảo đảm kiểm tra và cập nhật không bị race condition giữa nhiều request. Có thể thêm unique constraint cho mã, optimistic locking hoặc khóa phù hợp tùy mức độ đồng thời.

Không để command gọi trực tiếp JdbcTemplate hoặc JPA repository. Nếu làm vậy, quy tắc nghiệp vụ sẽ bị phân tán và khó bảo đảm nhất quán giữa các command.

## 16. Mở rộng nhóm command

Sau khi luồng cơ bản hoạt động, có thể bổ sung:

- **resource search:** tìm theo tên hoặc category.
- **resource history:** xem lịch sử bàn giao và thu hồi.
- **resource import:** nhập danh sách từ CSV.
- **resource export:** xuất danh mục sang CSV hoặc JSON.
- **resource stats:** thống kê số lượng theo trạng thái và category.
- **resource assign --to:** ghi nhận người nhận tài nguyên.

Khi thêm command, tiếp tục inject cùng ResourceCatalogService hoặc service chuyên trách được tách ra từ nghiệp vụ. Nếu command mới cần một quy tắc dùng chung, thêm method vào service thay vì lặp code.

Nếu nhóm lệnh lớn, có thể tách thành các class theo use case: write, query, lifecycle, import/export. Dùng cùng **@CommandGroup(prefix = "resource", name = "Quản lý tài nguyên")** để các command xuất hiện dưới cùng prefix và nhóm help.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Command không xuất hiện trong help | Class không nằm trong component scan hoặc annotation sai | Kiểm tra package và @CommandGroup |
| Prefix resource không được thêm | Method command khai báo sai hoặc group prefix không có | Kiểm tra @CommandGroup(prefix = "resource") |
| add tạo dữ liệu nhưng list không thấy | Mỗi command tự tạo một service hoặc một Map | Inject cùng ResourceCatalogService singleton |
| Spring báo nhiều bean service | Khai báo nhiều @Service hoặc @Bean trùng loại | Giữ một bean catalog hoặc dùng qualifier có chủ đích |
| Giá trị có dấu cách bị cắt | Không quote option value | Dùng --name="Laptop phòng họp" |
| status không chuyển đổi | Giá trị không khớp enum | Dùng AVAILABLE, IN_USE hoặc RETIRED |
| Không tìm thấy ID vừa tạo | ID bị gõ sai hoặc process đã khởi động lại | Xem lại ID; nhớ kho dữ liệu ví dụ chỉ ở bộ nhớ |
| Có thể xóa tài nguyên đang dùng | Kiểm tra nằm trong command khác thay vì service | Đặt invariant trong delete của service |
| Test phụ thuộc thứ tự | Dùng chung state giữa test | Tạo context/service mới hoặc reset fixture |
| Output các command không đồng nhất | Mỗi command tự định dạng | Dùng ResourceOutput chung |
| Dữ liệu mất khi thoát ứng dụng | Dùng ConcurrentHashMap trong bộ nhớ | Thay bằng repository/database |

## 18. Checklist hoàn thành

- [ ] Có domain model ResourceItem và ResourceStatus.
- [ ] Có một ResourceCatalogService được Spring quản lý.
- [ ] Service kiểm tra tên và category, sinh ID và quản lý trạng thái.
- [ ] Có command add, list, show, assign, release, retire và delete.
- [ ] Các command được nhóm dưới prefix resource.
- [ ] Nhiều command class cùng inject ResourceCatalogService.
- [ ] Không có Map hoặc danh mục riêng trong command class.
- [ ] Quy tắc không xóa tài nguyên IN_USE nằm trong service.
- [ ] Output được định dạng nhất quán.
- [ ] Đã chạy thử luồng tạo, xem, bàn giao, thu hồi, thanh lý và xóa.
- [ ] Đã kiểm thử service độc lập.
- [ ] Đã kiểm thử xuyên command bằng ShellTestClient.
- [ ] Đã hiểu dữ liệu ví dụ chỉ tồn tại trong vòng đời process.
- [ ] Có kế hoạch thay kho trong bộ nhớ bằng repository nếu cần persistence.

## Tài liệu tham khảo

- [Spring Shell 4 — Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) — annotation-based registration, Spring-managed command bean và CommandRegistry.
- [Spring Shell 4 — Organizing Commands](https://docs.spring.io/spring-shell/reference/commands/organize.html) — nhóm command bằng thuộc tính group.
- [Spring Shell 4 API — CommandGroup](https://docs.spring.io/spring-shell/reference/4.0-SNAPSHOT/api/org/springframework/shell/core/command/annotation/CommandGroup.html) — prefix và tên nhóm command.
- [Spring Shell 4 API — Command](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html) — khai báo command, alias, group và mô tả.
- [Spring Shell 4 API — Option](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Option.html) — shortName, longName, required và defaultValue.
- [Spring Shell 4 — Testing](https://docs.spring.io/spring-shell/reference/testing.html) — ShellTest, ShellTestClient và kiểm thử nhiều command trong cùng test context.
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide) — thay đổi command annotation, command group và command registration từ v3 sang v4.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html) — singleton scope mặc định và vòng đời bean được inject dùng chung trong application context.
