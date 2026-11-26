# So sánh thời gian test giữa các commit

## 1. Quality gate phải trả lời “test nào chậm hơn, chậm do đâu?”

Một pull request chỉnh sửa module `orders` làm job `./gradlew test` tăng từ 4 phút lên 7 phút. Nhìn hai con số rồi kết luận “test module chậm 75%” là **chưa đủ bằng chứng**: lần chạy mới có thể phải tải dependency, compile thêm source, khởi động Testcontainers lần đầu hoặc chạy nhiều test hơn. Ngược lại, thời gian tổng job gần như không đổi có thể che một `@ApplicationModuleTest` tăng từ 2 giây lên 15 giây trong lúc những test khác nhanh hơn.

Bài thuộc chương **CI và quality gate** của `SPRING_MODULITH_VERIFICATION_TESTING`: học phần rèn kiểm chứng ranh giới kiến trúc với `ApplicationModules`, thực hành `@ApplicationModuleTest`, kiểm thử sự kiện, cơ sở dữ liệu và tích hợp. Riêng bài này triển khai **quy trình đo, so sánh và cảnh báo thời gian test giữa các commit** mà không làm yếu những contract tests bắt buộc.

**Hợp đồng đo lường của bài:**

| Mã | Yêu cầu | Bằng chứng |
| --- | --- | --- |
| `TIME-01` | So sánh commit nền và commit PR trong điều kiện tương đương | SHA, JDK, runner, Gradle command và thứ tự lượt chạy |
| `TIME-02` | Mỗi commit có nhiều mẫu thời gian | Ít nhất 3 lượt đo, giữ riêng JUnit XML/log |
| `TIME-03` | Không nhầm thời gian build với thời gian test | Wall-clock Gradle và JUnit testcase time được báo riêng |
| `TIME-04` | Test bắt buộc không bị xóa/skip để “nhanh hơn” | Test identity và XML validation |
| `TIME-05` | Regression vượt ngưỡng gây quality gate đỏ | Median + ngưỡng tuyệt đối/tương đối |
| `TIME-06` | Có dữ liệu chẩn đoán, không chỉ một tỷ lệ phần trăm | Artifact per commit/per run, case mới/mất, startup/cache notes |

**Đích đo:** sau một thay đổi, trả lời được *test/nhóm nào tăng thời gian*, *có cùng phép thử và môi trường không*, *mức tăng có vượt nhiễu đo lường không*, và *CI cần báo hay chặn gì*. Không dùng câu “test chậm” làm lý do bỏ `ApplicationModules.verify()` hoặc giảm số lượng `@ApplicationModuleTest`.

## 2. Phân biệt ba loại thời gian trước khi so sánh

Có ba đồng hồ khác nhau:

| Chỉ số | Điểm bắt đầu/kết thúc | Nó bao gồm | Nó không tự cô lập |
| --- | --- | --- | --- |
| **Job duration** | Từ lúc runner bắt đầu job tới lúc hoàn tất | Checkout, setup JDK, cache, build, test, upload | Chi phí của riêng JUnit |
| **Gradle invocation wall time** | Trước/sau lệnh `./gradlew ... test` | Gradle startup/configuration, task dependencies, JVM forks và test | Chỉ riêng method test |
| **JUnit XML testcase time** | Theo JUnit/Gradle runner cho mỗi `testcase` | Phần runner tính cho một test invocation | Mọi chi phí context `@BeforeAll`, worker startup, compilation, broker/container startup |

Ví dụ cùng một PR có thể có:

| Đơn vị đo | Commit nền | Commit PR | Diễn giải |
| --- | ---: | ---: | --- |
| Job duration | 4m10s | 6m55s | Có regression ở toàn pipeline, chưa rõ nguồn |
| Gradle wall time | 185s | 290s | Có thể do compile/context/containers/test |
| `ModuleArchitectureTest` testcase | 0.9s | 0.9s | Kiểm tra architecture không chậm hơn |
| `OrdersModuleContractTest` testcase | 0.12s | 0.15s | Chênh rất nhỏ, dễ là nhiễu |
| `OrderEventIntegrationTest` testcase | 5.2s | 19.8s | Nên điều tra event/DB/test synchronization |

Các con số trên **chỉ minh họa**, không phải benchmark của Spring Modulith.

**Đặc biệt với `@ApplicationModuleTest`:** thời gian tạo `ApplicationContext` có thể được phân bổ vào lifecycle/test framework khác nhau tùy runner, Gradle/JUnit version và context cache. Không mặc định coi `<testcase time="...">` là **toàn bộ chi phí bootstrap module**. Muốn đo startup đầy đủ, cần nhìn Gradle task/wall time và log/context instrumentation tương ứng.

### Hai biểu đồ không nên gộp

- **Hiệu năng CI:** wall time tổng lệnh và job, có ích để đặt ngân sách phút/chi phí runner.
- **Hiệu năng một contract test:** JUnit testcase time hoặc suite time, có ích để tìm test bị regression.

Nếu một commit thêm 100 test mới, tổng suite có thể chậm hơn **mà từng test cũ không regress**. Báo rõ “tăng số phép kiểm” thay vì ép mọi trường hợp vào “test cũ chậm đi”.

## 3. Chốt giao thức đo: cùng bài test, cùng máy, lặp và đảo thứ tự

So sánh tối thiểu phải ghi:

- **BASE_SHA:** commit nền được chọn (ví dụ base của pull request).
- **HEAD_SHA:** commit đề xuất.
- **Environment:** runner image/CPU class, JDK vendor/version, Gradle wrapper, OS, JVM options và test profile.
- **Command:** cùng Gradle task, `--tests` filters, system properties và dependencies khả dụng.
- **Attempts:** ít nhất 3, tốt hơn 5–7 khi môi trường nhiễu và chi phí cho phép.
- **Order:** xen kẽ nền → PR, PR → nền để hạn chế lợi thế “lượt sau được cache/JIT nóng”.
- **Fixtures:** database, broker, Kafka consumer group, test keys và trạng thái container đủ isolation giữa lượt chạy.
- **Reports:** lưu file XML/log của từng SHA/lượt trước khi lần tiếp theo ghi đè.

Mô hình ba vòng minh họa:

```text
Khởi động runner và chuẩn bị hai worktree
  BASE_SHA  ---- testClasses warmup ----\
                                        +--- cùng JDK / cùng runner
  HEAD_SHA  ---- testClasses warmup ----/

Round 1: BASE -> HEAD
Round 2: HEAD -> BASE
Round 3: BASE -> HEAD

Lưu cho mỗi lượt:
  base/1/wall_seconds.txt + junit/ + gradle.log
  head/1/wall_seconds.txt + junit/ + gradle.log
  ...
```

**Vì sao warmup cả hai trước khi đo?** Tránh đưa phần lớn dependency download/compile lần đầu vào mẫu đo một cách lệch bên. Tuy nhiên, workflow dưới đây dùng `--rerun-tasks` để ép test chạy lại, nên Gradle vẫn tái thực thi **task dependencies**, có thể bao gồm biên dịch. Vì vậy `wall_seconds` là **wall time của lệnh build+test theo lựa chọn đo**, còn per-test JUnit XML là chỉ số khác. Đừng đặt nhãn `pure test time` cho wall time này.

### Những trường hợp “không so sánh được” phải báo riêng

1. BASE và HEAD dùng JDK hoặc Gradle wrapper khác nhau đáng kể.
2. Test class/method bị đổi tên hoặc xóa; thiếu common identity để ghép cặp.
3. HEAD thêm integration test mới; tổng duration tăng do **phạm vi test tăng**.
4. Một lượt bị lỗi assertion, timeout hoặc infrastructure—đây là **test failure**, không được biến thành mẫu benchmark hợp lệ.
5. Test suite dùng state shared và lượt sau thừa hưởng dữ liệu lượt trước.
6. PR thay cấu hình parallel forks, JVM args hoặc Testcontainers topology.
7. Cache từ lượt trước làm thứ tự đo chi phối kết quả.

Có thể vẫn thu thập hai bộ số đo trong các trường hợp này, nhưng gắn cờ **incomparable** hoặc yêu cầu điều tra; không kết luận một regression chính xác từ các mẫu chưa cùng điều kiện.

## 4. Tạo hai phép thử Spring Modulith có identity ổn định

Một phép đo chỉ có ý nghĩa khi kiểm thử **hợp đồng thật**, không phải một test được `@Disabled` để làm đường thời gian đẹp hơn. Ta dùng hai class JUnit ổn định: kiến trúc và hành vi module.

Cấu trúc ví dụ:

```text
com.example.shop/
├── ShopApplication.java
├── inventory/StockAvailability.java
└── orders/
    ├── OrderPlaced.java
    ├── OrderService.java
    └── OrderModuleContractTest.java       // ở src/test/java

src/test/java/com/example/shop/ModuleArchitectureTest.java
```

Application root:

```java
// src/main/java/com/example/shop/ShopApplication.java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Port công khai ở module `inventory`:

```java
// src/main/java/com/example/shop/inventory/StockAvailability.java
package com.example.shop.inventory;

public interface StockAvailability {
    boolean available(String sku);
}
```

API và service của `orders`:

```java
// src/main/java/com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

public record OrderPlaced(String orderId, String sku) {
}
```

```java
// src/main/java/com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import com.example.shop.inventory.StockAvailability;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final StockAvailability inventory;
    private final ApplicationEventPublisher events;

    public OrderService(
            StockAvailability inventory,
            ApplicationEventPublisher events) {
        this.inventory = inventory;
        this.events = events;
    }

    public boolean place(String orderId, String sku) {
        if (orderId == null || orderId.isBlank()
                || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                "Invalid orderId/sku");
        }

        if (!inventory.available(sku)) {
            return false;
        }

        events.publishEvent(new OrderPlaced(orderId, sku));
        return true;
    }
}
```

Khai báo chiều phụ thuộc:

```java
// src/main/java/com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.orders;
```

Architecture contract test **không bootstrap Spring context**:

```java
// src/test/java/com/example/shop/ModuleArchitectureTest.java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Module contract test nạp `orders`, thay port từ module khác bằng test double:

```java
// src/test/java/com/example/shop/orders/OrderModuleContractTest.java
package com.example.shop.orders;

import com.example.shop.inventory.StockAvailability;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@ApplicationModuleTest
class OrderModuleContractTest {

    @Autowired
    OrderService orders;

    @MockitoBean
    StockAvailability inventory;

    @Test
    void publishesWhenStockIsAvailable(PublishedEvents events) {
        given(inventory.available("SKU-1")).willReturn(true);

        assertThat(orders.place("ORD-1", "SKU-1"))
            .isTrue();

        assertThat(events.ofType(OrderPlaced.class))
            .singleElement()
            .satisfies(event -> {
                assertThat(event.orderId()).isEqualTo("ORD-1");
                assertThat(event.sku()).isEqualTo("SKU-1");
            });
    }
}
```

`@MockitoBean` yêu cầu Spring Framework 6.2+ với Boot/Modulith tương thích; các version cũ có thể cần `@MockBean`. Hai test trên kiểm **architecture** và **domain publication**, không chạy database hoặc Kafka. Khi đo thời gian một `@ApplicationModuleTest`, mục tiêu là nhận diện regression ở context/bootstrap và hành vi module, không “tối ưu” bằng cách loại bỏ `PublishedEvents` assertions.

### Khi test bị sửa giữa hai commit

Nếu đổi tên `publishesWhenStockIsAvailable`, comparator theo `classname#method` sẽ coi đó là **test bị mất + test mới**. Đây là kết quả đúng về identity; không được ngầm ghép hai test có tên khác để tạo một biểu đồ duration liên tục mà không có mapping được review.

## 5. Thu số liệu từ Gradle và JUnit XML, lưu riêng từng commit

Đầu ra Gradle Test thông thường:

```text
build/test-results/test/
├── TEST-com.example.shop.ModuleArchitectureTest.xml
└── TEST-com.example.shop.orders.OrderModuleContractTest.xml

build/reports/tests/test/
└── index.html
```

Một record JUnit XML thường có `<testcase classname="..." name="..." time="...">`; thuộc tính `time` thường biểu diễn **giây**. Nó phụ thuộc vào runner, nên kiểm tra file thực tế của project trước khi kết luận startup time thuộc test nào.

### Lệnh kiểm tra một commit tại local

```bash
# Build + chạy lại test có chủ đích để có report mới.
./gradlew --no-daemon --console=plain \
  --rerun-tasks test \
  --tests com.example.shop.ModuleArchitectureTest \
  --tests com.example.shop.orders.OrderModuleContractTest
```

Khi dùng `--rerun-tasks`, cả các task phụ thuộc có thể chạy lại; lệnh này phù hợp đo **chi phí của chính pipeline đã chọn**, nhưng không phải phép đo chỉ riêng JUnit. Để đo **test-only wall time** có thể thêm task benchmark Test chuyên biệt với `outputs.upToDateWhen { false }` và dependency `testClasses`, rồi dùng cùng task trên hai commit. Nếu thêm task ở HEAD mà BASE chưa có, phải backport cấu hình benchmark hoặc dùng một phép đo chung khác; không so sánh hai command khác nhau.

### Chú ý về cache và test selection

- Không dùng `./gradlew test` lặp lại rồi tin thời gian cực ngắn nếu Gradle trả `UP-TO-DATE`.
- Không vô hiệu hóa Gradle cache một bên mà giữ cache bên còn lại.
- Không thay `--tests` filter giữa BASE và HEAD nếu đang so sánh matched test identity.
- Không chỉ lưu `BUILD SUCCESSFUL`; phải giữ XML và kiểm số lượng test/case hợp lệ.
- Khi một test `@Disabled`, report có thể ghi `skipped` thay vì làm Gradle fail; comparator phải phát hiện và từ chối mẫu ấy.
- Nếu `ApplicationModules.verify()` fail, đó là **lỗi kiến trúc**, không phải “regression thời gian” cần chạy lại cho xanh.

## 6. GitHub Actions đo BASE và HEAD trên cùng runner

Ví dụ workflow bên dưới hoạt động cho một **Gradle single-project** trên Linux, đo cùng hai class test ở phần 4. Nó tạo hai Git worktrees theo SHA của pull request, chuẩn bị compile cả hai, rồi đo **ba lượt xen kẽ**. Mỗi lượt giữ XML/log trước khi chạy lại.

Đặt script phân tích ở `ci/compare_test_durations.py` theo phần 7 khi tích hợp thật. **Nhiệm vụ viết bài này không tạo script/workflow ngoài Markdown.**

```yaml
# Minh họa: .github/workflows/test-duration-compare.yml
name: Compare Modulith test duration

on:
  pull_request:

permissions:
  contents: read

jobs:
  duration-compare:
    name: Modulith duration comparison
    runs-on: ubuntu-latest
    timeout-minutes: 50

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v4

      - name: Measure BASE and HEAD
        shell: bash
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
        run: |
          set -euo pipefail

          root="$RUNNER_TEMP/test-times"
          mkdir -p "$root"

          git worktree add --detach \
            "$RUNNER_TEMP/src-base" "$BASE_SHA"
          git worktree add --detach \
            "$RUNNER_TEMP/src-head" "$HEAD_SHA"

          # Chuẩn bị code/dependencies trước các lượt đo.
          for name in base head; do
            (
              cd "$RUNNER_TEMP/src-$name"
              ./gradlew --no-daemon --console=plain \
                testClasses > "$root/compile-$name.log" 2>&1
            )
          done

          for round in 1 2 3; do
            if [ "$round" -eq 2 ]; then
              order="head base"
            else
              order="base head"
            fi

            for name in $order; do
              (
                cd "$RUNNER_TEMP/src-$name"
                out="$root/$name/$round"
                mkdir -p "$out"

                start=$(date +%s%N)

                ./gradlew --no-daemon --console=plain \
                  --rerun-tasks test \
                  --tests com.example.shop.ModuleArchitectureTest \
                  --tests com.example.shop.orders.OrderModuleContractTest \
                  > "$out/gradle.log" 2>&1

                end=$(date +%s%N)

                awk -v start="$start" -v end="$end" \
                  'BEGIN {
                    printf "%.3f\n",
                      (end - start) / 1000000000
                  }' > "$out/wall_seconds.txt"

                cp -R build/test-results/test "$out/junit"
              )
            done
          done

      - name: Compare medians and enforce timing budget
        run: >
          python3 ci/compare_test_durations.py
          "$RUNNER_TEMP/test-times"

      - name: Upload raw timing evidence
        if: ${{ always() }}
        uses: actions/upload-artifact@v4
        with:
          name: modulith-test-time-comparison
          path: ${{ runner.temp }}/test-times/
          if-no-files-found: warn
          retention-days: 7
```

### Điều workflow **thực sự** đo

- `BASE_SHA` và `HEAD_SHA` cùng chạy trên một runner/JDK. Không tuyên bố hai worktrees có cùng Gradle wrapper nếu PR đổi wrapper; **phải kiểm tra phiên bản khi đọc kết quả**.
- `testClasses` là bước chuẩn bị, không đưa vào `wall_seconds.txt`. Nhưng `--rerun-tasks` có thể chạy lại compile trong lệnh đo, nên wall time vẫn chứa task dependencies.
- Mỗi vòng đổi thứ tự, giảm một phần warm-cache/order bias nhưng không loại hết nhiễu vì runner/GC/containers vẫn có thể khác.
- Lệnh test fail thì step sẽ FAIL với `set -e`; đó là **failure cần điều tra**, không được đưa duration của lượt fail vào đường so sánh như một PASS. Artifact từ các lượt đã hoàn tất vẫn được upload.
- Test suites có PostgreSQL/Kafka cần cleanup/isolation trước mỗi lượt và có thể cần tổng timeout khác; workflow chỉ minh họa hai contract tests không dùng DB/broker.
- `pull_request` chạy code từ PR trong runner với quyền `contents: read`, không cung cấp production secrets; **không dùng `pull_request_target` để thực thi code PR tùy ý**.

Đây là **mẫu đo** cần được chạy thử và hiệu chỉnh ở CI thực, không phải con số bảo đảm cho mọi Gradle/Spring Boot version. Nếu BASE đã xóa class test đang lọc, workflow phải báo **không đủ dữ liệu so sánh** và yêu cầu quyết định khác, thay vì đổi filter âm thầm.

## 7. Script phân tích: median, matched tests và ngưỡng regression

Đây là script Python chuẩn, không cần thư viện ngoài. Nó đọc ba lần JUnit XML và wall seconds cho mỗi SHA, kiểm tra test bắt buộc có chạy, từ chối test fail/skip, phát hiện test bị xóa, rồi dùng **median** để giảm tác động của một mẫu thời gian bất thường.

**Ngưỡng minh họa, cần được phê duyệt theo dự án:**

- Testcase regression khi HEAD median lớn hơn BASE **trên 50%** *và* tăng tuyệt đối **trên 1 giây**.
- Gradle wall regression khi HEAD median lớn hơn BASE **trên 30%** *và* tăng tuyệt đối **trên 20 giây**.
- Một required test biến mất → FAIL dù thời gian tổng giảm.
- Test mới → báo riêng, không kết luận test cũ regress chỉ vì suite nhiều test hơn.

```python
# ci/compare_test_durations.py
from __future__ import annotations

from pathlib import Path
from statistics import median
import sys
import xml.etree.ElementTree as ET

ROUNDS = (1, 2, 3)
REQUIRED = {
    "com.example.shop.ModuleArchitectureTest"
    "#verifiesModuleBoundaries",
    "com.example.shop.orders.OrderModuleContractTest"
    "#publishesWhenStockIsAvailable",
}


def read_attempt(root: Path, label: str, number: int):
    folder = root / label / str(number)
    junit = folder / "junit"
    files = list(junit.rglob("TEST-*.xml"))

    if not files:
        raise ValueError(f"No JUnit XML: {label}/{number}")

    cases: dict[str, float] = {}

    for file in files:
        tree = ET.parse(file)

        for case in tree.getroot().iter("testcase"):
            klass = case.attrib.get("classname", "")
            name = case.attrib.get("name", "")
            key = f"{klass}#{name}"

            if not klass or not name:
                raise ValueError(f"Invalid testcase: {file}")

            if any(
                child.tag.rsplit("}", 1)[-1]
                in {"failure", "error", "skipped"}
                for child in case
            ):
                raise ValueError(
                    f"Non-passing test {key} in {file}"
                )

            if key in cases:
                raise ValueError(
                    f"Duplicate test identity {key}"
                )

            cases[key] = float(case.attrib["time"])

    missing = REQUIRED - cases.keys()
    if missing:
        raise ValueError(
            f"Missing required tests {label}/{number}: "
            f"{sorted(missing)}"
        )

    wall = float(
        (folder / "wall_seconds.txt")
        .read_text(encoding="utf-8").strip()
    )
    return cases, wall


def main(root: Path):
    samples = {
        label: [
            read_attempt(root, label, n)
            for n in ROUNDS
        ]
        for label in ("base", "head")
    }

    # Mỗi lần đo của cùng một commit phải có tập test
    # nhất quán; khác test selection là lỗi dữ liệu đo.
    for label, runs in samples.items():
        expected = set(runs[0][0])
        for cases, _ in runs[1:]:
            if set(cases) != expected:
                raise ValueError(
                    f"Inconsistent test identities for {label}"
                )

    base_ids = set(samples["base"][0][0])
    head_ids = set(samples["head"][0][0])

    removed = base_ids - head_ids
    added = head_ids - base_ids
    common = sorted(base_ids & head_ids)

    print(f"Matched tests: {len(common)}")
    print(f"Added tests: {sorted(added)}")
    print(f"Removed tests: {sorted(removed)}")

    failures = []

    if removed:
        failures.append(
            f"Removed tests require review: {sorted(removed)}"
        )

    for key in common:
        b = median(
            cases[key]
            for cases, _ in samples["base"]
        )
        h = median(
            cases[key]
            for cases, _ in samples["head"]
        )

        print(
            f"{key}: base={b:.3f}s, "
            f"head={h:.3f}s, delta={h-b:+.3f}s"
        )

        if h > b * 1.50 and h - b > 1.0:
            failures.append(
                f"Test time regression: {key}"
            )

    base_wall = median(
        wall for _, wall in samples["base"]
    )
    head_wall = median(
        wall for _, wall in samples["head"]
    )

    print(
        "Gradle wall median: "
        f"base={base_wall:.3f}s "
        f"head={head_wall:.3f}s "
        f"delta={head_wall-base_wall:+.3f}s"
    )

    if (
        head_wall > base_wall * 1.30
        and head_wall - base_wall > 20.0
    ):
        failures.append("Gradle wall regression")

    if not common:
        failures.append("No comparable test identities")

    for reason in failures:
        print(f"QUALITY GATE FAIL: {reason}")

    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(Path(sys.argv[1])))
    except (OSError, ValueError, KeyError) as exc:
        print(f"INVALID MEASUREMENT: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
```

### Cách hiểu kết quả

- **Exit 0:** không phát hiện regression vượt **hai ngưỡng** đã đặt trong matched tests/wall; **không có nghĩa performance hoàn hảo**.
- **Exit 1:** ít nhất một regression vượt budget hoặc test đã có ở BASE biến mất.
- **Exit 2:** dữ liệu đo không hợp lệ (XML thiếu, test skipped/failed, case identity lặp, thiếu file), cần sửa measurement/test trước khi kết luận.
- Các test mới được liệt kê nhưng không ghép giả tạo với testcase khác.
- Median theo **từng test** giúp thấy regression có thể bị che trong tổng suite. Median wall giúp thấy chi phí build+test kể cả khi per-method time không đổi.

### Một giới hạn phải nói thẳng

Script demo không tính phân phối thống kê, confidence interval, container warmup, correlation hay sự khác nhau về hardware theo runner. Ba lượt/median và hai ngưỡng là **quality gate đơn giản** để bắt regression rõ; với suite nhiều nhiễu hoặc thay đổi nhỏ, hãy tăng mẫu, phân tích variance/p95 và yêu cầu điều tra thay vì ép một threshold “chuẩn” cho mọi test.

Việc **bỏ test ở HEAD làm gate đỏ** là chính sách nhằm ngăn “tối ưu bằng xóa test”. Nếu rename có chủ đích, cập nhật mapping identity/contract inventory sau review; không xóa rule chỉ để có số đo đẹp.

## 8. Đọc khác biệt đúng trong Spring Modulith: context, event, DB

Một test module chậm hơn không nhất thiết là use case chậm hơn. Cần phân loại nguồn:

| Hiện tượng | Bằng chứng cần tìm | Hướng xử lý |
| --- | --- | --- |
| `ApplicationModules.verify()` lâu hơn | XML/wall architecture class, classpath size | Xem module discovery/package scope, classpath; **không bỏ verification** |
| `@ApplicationModuleTest` lâu sau thêm `@Import` | Context logs, bean count, auto-configuration | Giữ context đúng phạm vi module, không import nặng tùy tiện |
| Context cache hit ở một commit, miss ở commit khác | Test order, profiles, `@MockitoBean`, `@DirtiesContext` | So sánh trong điều kiện tương đương và tách startup costs |
| Test `PublishedEvents` bỗng chậm | Business code, listener đồng bộ, event count | Đo đường publish; kiểm tra listener trong phạm vi module |
| Test `@ApplicationModuleListener` chậm | Thread scheduling, async queue, Awaitility timeout | Chờ điều kiện nghiệp vụ; phân biệt latency và timeout |
| `@TransactionalEventListener(AFTER_COMMIT)` chờ lâu | Thời điểm commit, DB locks, listener work | Đo transaction/commit và handler tách riêng |
| Testcontainers cold start | Logs container, image pull/readiness | Cố định image, chuẩn bị image/cache và lifecycle |
| JPA integration chậm | Query count, migration time, flush/commit | Kiểm tra DB thực, indexing/fixture; không thay bằng mock |
| Test mới thêm làm suite lâu hơn | Added test identities và total cases | Đánh giá giá trị/chi phí test mới, không gán regression cho test cũ |
| Gradle wall tăng nhưng XML không tăng | Compile/configuration/dependency/worker startup | Đọc `--profile`/build logs, không “tối ưu” JUnit assertions |

### Context cache và test ordering

Spring TestContext có thể cache `ApplicationContext` giữa các test class cấu hình tương thích. Nếu một lượt đo chạy `OrderModuleContractTest` trước class khác, còn lượt khác chạy sau khi context đã nóng, thời gian testcase có thể thay đổi mà code nghiệp vụ không đổi. Vì vậy:

- Giữ cùng test selection và runner parallelism giữa các commit.
- Khi muốn so sánh **cold bootstrap**, cô lập context/worker process có chủ đích; không để một bên warm, một bên cold.
- Khi muốn so sánh **chi phí thường gặp của CI**, dùng chính thứ tự và cache policy mà CI áp dụng.
- Không thêm `@DirtiesContext` khắp nơi chỉ để buộc cold start; annotation này có thể làm suite chậm và đổi hành vi cache thật.
- Xem JUnit XML cùng wall/log/context metrics, không suy toàn bộ bootstrap cost từ một method time.

### Event/DB integration cần phép đo bổ sung

`PublishedEvents` xác nhận domain event đã được công bố, nhưng không chờ Kafka broker ack. Nếu mục tiêu là thời gian **order confirmed → notification persisted**, phải đo từ business event tới state sau commit trong test tích hợp, với transaction, consumer và database thật, không đo mỗi method publish rồi cho rằng end-to-end latency được bảo vệ.

Khi production chuyển từ listener đồng bộ sang bất đồng bộ, testcase time có thể **giảm** vì method trả sớm, nhưng latency hoàn tất nghiệp vụ có thể **tăng**. Quality gate phải bám chỉ số đúng: **thời gian xử lý hoàn tất**, không thưởng cho việc trả về trước khi làm xong.

## 9. Thiết kế budget và thử “mutation” để biết gate có hiệu lực

### Ngưỡng cần phù hợp loại test

| Loại | Chỉ số gợi ý | Policy ví dụ |
| --- | --- | --- |
| Architecture `verify()` | Testcase/suite time và task wall | Báo khi tăng đáng kể; vẫn luôn chạy |
| `@ApplicationModuleTest` | Median per-test, số context load | Chặn tăng lớn, kiểm tra context scope |
| DB/Kafka integration | Median + p95/p99 khi đủ mẫu, timeout rate | Budget riêng vì nhiễu và tài nguyên |
| Full PR suite | Gradle wall và job duration | Ngưỡng phút/chi phí runner do đội vận hành chọn |
| Async event processing | Time-to-business-completion | Không dùng method-return time thay cho completion |

Script mẫu ở phần 7 dùng cùng threshold chung để dễ triển khai. Khi áp dụng thật có thể cấu hình budget theo **test class/nhóm** nhưng phải giữ một chính sách có owner, được review và không hạ ngưỡng theo hướng che regression.

### Negative drill: cố ý thêm 2,5 giây vào một test

Trên một branch thử nghiệm, thêm đoạn này **vào đầu** method `publishesWhenStockIsAvailable` rồi revert:

```java
// CHỈ DÙNG ĐỂ KIỂM GATE TRÊN NHÁNH THỬ NGHIỆM.
Thread.sleep(2500L);
```

Vì method hiện chưa khai báo `throws`, khi thử thực tế có thể sửa signature:

```java
@Test
void publishesWhenStockIsAvailable(
        PublishedEvents events) throws InterruptedException {

    Thread.sleep(2500L);  // Phản ví dụ có chủ đích.
    // ... những assertions publication giữ nguyên ...
}
```

**Kỳ vọng:**

1. Cả BASE và HEAD đều chạy đủ test, không có `skipped`.
2. HEAD testcase median tăng khoảng 2,5 giây so với BASE.
3. Với điều kiện `h > b*1.50` và `h-b > 1.0s`, comparator trả **exit 1**.
4. Workflow **Module duration comparison** đỏ khi branch ruleset yêu cầu check.
5. Artifact vẫn có XML/log/timing của từng lượt, để xác định regression từ method nào.
6. Revert sleep, đo lại: chênh lệch không còn đáng kể, gate trở lại PASS.

Thí nghiệm này kiểm tra **bộ thu mẫu và ngưỡng per-test**, không chứng minh production code bị chậm. Chỉ dùng trên branch tạm; không cho `Thread.sleep` vào suite thật để “ổn định” async test.

### Trường hợp phải trả “incomparable”, không “PASS”

- Thay JVM/Gradle wrapper và không có đánh giá ảnh hưởng.
- Class test bắt buộc bị rename/xóa hoặc skipped.
- Một commit bật thêm/loại hạ tầng Kafka, Postgres, hoặc đổi số worker forks.
- Một lượt test fail vì assertion/timeout.
- Base/head dùng dữ liệu/điều kiện khác nhau.

Nếu môi trường khác biệt là một phần thay đổi **cần đánh giá**, có thể thực hiện benchmark compatibility riêng trong môi trường ghim version; đừng đổi số đo thành bằng chứng performance regression cùng điều kiện khi thực tế không cùng điều kiện.

## 10. CI checklist và Definition of Done

### Checklist cho một pull request làm chậm test

- [ ] Đã ghi `BASE_SHA` và `HEAD_SHA` chính xác; không chỉ so ảnh thời gian của hai GitHub jobs khác ngày.
- [ ] Cùng runner/JDK/Gradle command; khác wrapper/config được nhận diện và review.
- [ ] Test được chọn giống nhau; test thêm/xóa được báo riêng.
- [ ] Có ít nhất 3 mẫu/commit, thứ tự đo xen kẽ; quy định warmup/cache rõ.
- [ ] `./gradlew test` không bị báo `UP-TO-DATE` mà không thực thi test.
- [ ] Mỗi mẫu có exit code PASS và JUnit XML; test skipped/failure không được dùng làm measurement.
- [ ] Có wall time của lệnh và per-test JUnit time, không trộn làm một chỉ số.
- [ ] So sánh median cùng test identity; budget gồm ngưỡng tương đối và tuyệt đối.
- [ ] Không suy method time là toàn bộ context/bootstrap latency.
- [ ] Với `@ApplicationModuleTest`, đã xem context scope/`@Import`/mock/profile/cache khi thời gian tăng.
- [ ] Với event async/JPA, đo tới business completion/commit khi đó mới là contract.
- [ ] `ApplicationModules.verify()` và `PublishedEvents` assertions **không bị bỏ** để tăng tốc.
- [ ] Script phân biệt **regression**, **incomparable data** và **test failure**.
- [ ] CI lưu XML/log theo commit và lượt; không rò secret/PII trong artifact.
- [ ] Job thời gian là required check nếu policy chặn regression; branch protection được cấu hình đúng.
- [ ] Đã thử mutation `Thread.sleep(2500)`, thấy gate đỏ, sau revert thấy gate xanh.
- [ ] Threshold, owner và cách xử lý exception/waiver được ghi nhận; không âm thầm nâng budget.

### Bài tập tự kiểm tra

**A.** BASE có 20 tests/150 giây; HEAD có 30 tests/190 giây. Có được kết luận test cũ chậm 27% không?  
**Không.** HEAD thêm 10 tests; phải ghép matched test identities và tách tổng suite time khỏi test-level regression.

**B.** Gradle wall tăng 40 giây nhưng mỗi JUnit testcase time giữ nguyên. Tầng nào cần kiểm?  
**Gradle build/configuration, compile, worker/context startup, cache và test selection**; không vội sửa assertions.

**C.** `OrderModuleContractTest` giảm từ 10 giây còn 0,1 giây vì developer thêm `@Disabled` vào test chậm. CI có được PASS không?  
**Không.** Đây là mất kiểm chứng. Comparator phải từ chối skipped/removed required tests, dù con số đẹp hơn.

**D.** Một listener đổi sang async khiến `orders.place(...)` trả nhanh hơn, nhưng notification được ghi sau 30 giây. Performance đã tốt hơn chưa?  
**Chưa thể kết luận.** Cần xác định SLA: nếu cam kết business outcome sau commit, phải đo end-to-end completion latency.

### Definition of Done

Một quality gate **so sánh thời gian test giữa các commit** đạt yêu cầu khi:

1. **Tái lập được:** có commit SHA, command, environment và test identities.
2. **Có dữ liệu đủ:** nhiều mẫu, XML/wall metrics và artifact theo lượt.
3. **So sánh có nghĩa:** ghép test cũ, tách test mới, dùng median và ngưỡng có chủ đích.
4. **Không thưởng cho việc giảm kiểm chứng:** xóa/skip test hoặc assertion sai khiến gate không hợp lệ.
5. **Dẫn tới hành động:** chênh lệch được phân loại theo Gradle, context, module, event/DB/integration.
6. **Chặn hồi quy rõ rệt:** regression vượt budget làm required check đỏ; measurement không hợp lệ cũng không pass.

**Ghi nhớ:** so sánh thời gian test giữa hai commit không phải lấy *hai con số job duration rồi trừ nhau*. Hãy chạy cùng hợp đồng trên BASE và HEAD trong điều kiện tương đương, lưu nhiều mẫu JUnit và wall-clock, ghép theo test identity, xem median cùng ngưỡng nhiễu, và buộc CI phát hiện **test bị mất/skip**. Với Spring Modulith, cách làm này giúp tối ưu `@ApplicationModuleTest`, context và event/database integration **mà vẫn giữ đầy đủ architecture và event quality gates**.
