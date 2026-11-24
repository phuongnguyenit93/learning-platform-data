# Distinguishing Discovery Order from Application-Defined Priority Order

## 1. Two Distinct Concepts

In Java, ServiceLoader locates implementations (providers) of a service interface. When iterating through the iterator, we observe a provider order. This is the **discovery order**, influenced by metadata, classloaders, modules, and packaging. It is not a business priority policy.

**Application priority** consists of rules defined by the host to select a suitable provider: support conditions, allowlisting configuration, priority levels, tie-breaking rules, and behavior when no candidate matches.

For example, an application has three exporters: DefaultExporter, CsvExporter, and FastCsvExporter. The provider that appears first is not necessarily the best exporter for a CSV request. If the application uses ServiceLoader.iterator().next() as the “default”, changing dependencies or merging JARs can alter the selection without changing any business code.

Two questions must be kept separate:

1. **Who is available?** Answered by ServiceLoader and the runtime environment.
2. **Who is selected for this request?** Answered by the application's policy.

## 2. Origins of Discovery Order

### Classpath and META-INF/services

On the classpath, providers can be declared in a file:

\`\`\`text
META-INF/services/com.example.spi.Exporter
\`\`\`

The contents are the binary names of the providers, one per line:

\`\`\`text
com.example.plugins.BasicExporter
com.example.plugins.FastExporter
\`\`\`

Within a single service-configuration file, line order is the declaration order. However, an application may see multiple files of the same name across multiple JARs. The order in which the classloader locates these resources depends on loading configuration, the JARs, and the deployment mechanism. When creating a shaded/uber JAR, merging service descriptors can also affect visibility order.

**Do not use position in the descriptor or classpath as priority** unless it is an actively controlled deployment contract with clear specifications and tests. In extensible plugin systems, a selection policy independent of discovery order is easier to maintain.

### Named modules

With the Java Platform Module System (JPMS), a named module can register a provider using a provides ... with ... declaration in module-info.java. The order in which providers are found when traversing modules is not a business priority scale. Test in the actual deployment module layer rather than assuming module path order reflects priority.

### Cache and reload

ServiceLoader may cache provider instances while iterating; reload() clears this cache, and previous iterators/streams become invalid. Even if a subsequent traversal sees a similar order, caching/reload does not define a priority policy. To change priority, you must change the application's policy or configuration data.

## 3. Designing a Deterministic Selector

A transparent strategy consists of four steps:

1. Discover the set of providers the host is permitted to use.
2. **Filter** candidates by task-support capability and allowlist conditions.
3. **Rank** eligible candidates according to the priority levels defined by the host.
4. **Break ties** using a stable rule or fail with an error when ambiguous.

For example: higher priority wins; on equal priority, provider IDs are compared in ascending alphabetical order; provider IDs must be unique. When no valid provider exists, the system throws an error with a clear message.

Example table:

| Provider | Supports text | Priority | Selected for text? |
| --- | --- | ---: | --- |
| basic | Yes | 10 | No, because lower |
| smart | Yes | 100 | Yes |
| image | No | 200 | No, because unsupported |

A provider that does not support the task must be excluded **before comparing priorities**, even if it has the highest priority number.

## 4. Runnable Java 17+ Example

The example separates the service API, two implementations, and the selector. It intentionally places the lower-priority provider first in META-INF/services to prove that selection does not depend on discovery order.

Directory structure:

\`\`\`text
sample/
  src/
    demo/spi/Formatter.java
    demo/plugins/BasicFormatter.java
    demo/plugins/SmartFormatter.java
    demo/Main.java
  resources/
    META-INF/services/demo.spi.Formatter
\`\`\`

**src/demo/spi/Formatter.java**

\`\`\`java
package demo.spi;

public interface Formatter {
    String id();
    int priority();
    boolean supports(String requestedFormat);
    String format(String input);
}
\`\`\`

**src/demo/plugins/BasicFormatter.java**

\`\`\`java
package demo.plugins;

import demo.spi.Formatter;

public final class BasicFormatter implements Formatter {
    public BasicFormatter() {}

    public String id() { return "basic"; }
    public int priority() { return 10; }
    public boolean supports(String requestedFormat) {
        return "text".equals(requestedFormat);
    }
    public String format(String input) {
        return "basic:" + input;
    }
}
\`\`\`

**src/demo/plugins/SmartFormatter.java**

\`\`\`java
package demo.plugins;

import demo.spi.Formatter;

public final class SmartFormatter implements Formatter {
    public SmartFormatter() {}

    public String id() { return "smart"; }
    public int priority() { return 100; }
    public boolean supports(String requestedFormat) {
        return "text".equals(requestedFormat);
    }
    public String format(String input) {
        return "smart:" + input;
    }
}
\`\`\`

**resources/META-INF/services/demo.spi.Formatter**

\`\`\`text
demo.plugins.BasicFormatter
demo.plugins.SmartFormatter
\`\`\`

**src/demo/Main.java**

\`\`\`java
package demo;

import demo.spi.Formatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    private static final Comparator<Formatter> RANKING =
            Comparator.comparingInt(Formatter::priority)
                    .reversed()
                    .thenComparing(Formatter::id);

    static Formatter choose(Iterable<Formatter> providers, String requested) {
        List<Formatter> eligible = new ArrayList<>();
        Set<String> ids = new HashSet<>();

        for (Formatter candidate : providers) {
            if (!ids.add(candidate.id())) {
                throw new IllegalStateException(
                        "Duplicate provider ID: " + candidate.id());
            }
            if (candidate.supports(requested)) {
                eligible.add(candidate);
            }
        }

        return eligible.stream()
                .min(RANKING)
                .orElseThrow(() -> new NoSuchElementException(
                        "No provider for " + requested));
    }

    public static void main(String[] args) {
        List<Formatter> providers = new ArrayList<>();
        for (Formatter candidate : ServiceLoader.load(Formatter.class)) {
            providers.add(candidate);
        }

        System.out.println("Discovery order:");
        for (Formatter candidate : providers) {
            System.out.println(candidate.id() + " priority="
                    + candidate.priority());
        }

        Formatter selected = choose(providers, "text");
        System.out.println("Selected: " + selected.id());
        System.out.println("Value: " + selected.format("hello"));

        Collections.reverse(providers);
        System.out.println("Selected after reverse: "
                + choose(providers, "text").id());
    }
}
\`\`\`

Compile and run from the sample directory in bash:

\`\`\`bash
mkdir -p out
javac -d out src/demo/spi/Formatter.java src/demo/plugins/BasicFormatter.java src/demo/plugins/SmartFormatter.java src/demo/Main.java
cp -R resources/. out/
java -cp out demo.Main
\`\`\`

Output with the metadata in the example:

\`\`\`text
Discovery order:
basic priority=10
smart priority=100
Selected: smart
Value: smart:hello
Selected after reverse: smart
\`\`\`

The example policy ranks by descending priority and ascending ID. Java Comparator.min(RANKING) selects the first element according to that comparator. A higher number wins. When reversing the input list order, the result does not change.

On Windows, replace mkdir -p and cp -R with the corresponding PowerShell commands, or use git bash; javac and java run as usual.

**Note:** implementations do not decide the policy themselves; they provide priority data via the interface, while the host decides how to read and compare it. Another host may use a configuration file to override it.

## 5. Distinguishing Wrong and Right Selection Approaches

### Wrong: picking the first provider

\`\`\`java
Formatter selected = ServiceLoader.load(Formatter.class)
        .iterator()
        .next();
\`\`\`

This snippet can throw NoSuchElementException if there are no providers, and if there are, it takes the first element in encounter order. It does not check supports(), does not use priority(), and has no tie-break.

Similarly, calling stream().findFirst() directly on the provider stream only selects according to the current encounter order.

### Right: filter then rank by policy

\`\`\`java
Formatter selected = ServiceLoader.load(Formatter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(provider -> provider.supports("text"))
        .min(Comparator.comparingInt(Formatter::priority)
                .reversed()
                .thenComparing(Formatter::id))
        .orElseThrow();
\`\`\`

This is a snippet to place inside a method with appropriate imports; if duplicate ID checks are needed, add a validation step like the choose() method in the complete example. The stream creates instances to read priority() and supports(); this instantiation cost must be considered.

### When priorities are equal

If the comparator only compares priority, two providers at the same level may be chosen based on input order. When determinism is required, the application must add a stable tie-break, such as a unique ID. If IDs collide, fail fast to avoid ambiguous identification.

If the application wants to treat “two plugins both have priority 100” as a configuration error, validate the conflict instead of automatically choosing by ID. That is also a clear policy.

## 6. Host-Owned Policy

It is not always advisable to let each provider decide its own priority. With third-party plugins, an implementation might set a very high priority just to always win. The host can store configuration instead:

\`\`\`yaml
providers:
  preferred: smart
  fallback:
    - basic
\`\`\`

This is an illustrative schema; the application must define its own parser and validation. It is necessary to decide clearly: must preferred be present? If the preferred plugin does not support the request, fall back or fail? If fallback contains non-existent IDs, is that acceptable?

A common policy is: the application verifies eligibility first, selects the configured provider if valid; if there is no mandatory selection, uses priority; when there are no candidates, reports an error. Decisions belong to the application contract and must not be inferred from ServiceLoader.

## 7. Priority Does Not Mean Eager Instantiation

ServiceLoader discovers providers on demand. When using an iterator to traverse all candidates, retrieving instances may instantiate multiple providers even though only one provider is selected.

If instantiation is expensive, consider:

- Using static metadata in a host-managed descriptor/config registry.
- Using ServiceLoader.stream() and Provider.type() to filter by type/annotation information before calling Provider.get().
- Clearly separating plugin metadata from the plugin runtime instance.

However, Provider.type() does not automatically provide priority() if priority is an instance method. For named modules using provider factory methods, type() may return the factory method's return type. Do not apply classpath provider assumptions to every module.

In addition, ServiceLoader is not thread-safe; manage the loader/provider lifecycle and synchronize if accessed by multiple threads.

## 8. Testing to Prove Stable Results

Cases that should be automated:

| Case | Expectation |
| --- | --- |
| basic priority 10 appears before smart priority 100 | smart wins |
| Reverse discovery order | smart still wins |
| High priority but supports() returns false | Another matching provider wins |
| Two equal priorities, different IDs | Tie-break works |
| Two duplicate IDs | Error is reported |
| No matching provider | Clear error is reported |
| Configured preferred does not exist | Fail fast or fall back per policy |
| Relocated/shaded JAR | ServiceLoader still discovers all providers |

A selector accepting Iterable/Collection is easier to test with synthetic data than a selector that loads the classpath itself. After unit testing the policy, run integration tests on the actual packaged artifact to verify service descriptors, provider classes, and classloaders.

When new plugin versions arrive, keep list-permutation tests and tie-break tests. This step protects the application against silent changes in dependency order.

## 9. Common Mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Using iterator().next() as policy | Selects by discovery order | Filter and rank |
| Using findFirst() before filter/sort | May select the wrong provider | Apply eligibility conditions and ranking first |
| No tie-breaker | Depends on encounter order on ties | Tie-break or report an error |
| Not checking for duplicate IDs | Ambiguous provider | Validate IDs |
| High priority despite not supporting | Selects an incapable provider | Filter eligibility first |
| Testing only inside the IDE | Misses JAR metadata errors | Test the final artifact |
| Letting plugins set uncontrolled priorities | Hard for host to keep policy stable | Cap priorities or use host configuration |
| Ignoring constructor cost during ranking | Instantiates too many plugins | Use metadata or appropriate discovery design |

## 10. Implementation Checklist

- [ ] Clearly define the service interface and the set of valid providers.
- [ ] Define priority and eligibility policies separately from discovery.
- [ ] Add a tie-breaker or ambiguity error for equal priorities.
- [ ] Mandate unique IDs with validation.
- [ ] Test results when reversing list order.
- [ ] Test fallback policy and unsupported providers.
- [ ] Test the final JAR artifact with ServiceLoader.
- [ ] Do not assume classpath/module path order is priority order.

**Remember:** ServiceLoader tells you which providers were found; the application is responsible for choosing which provider is used. A deterministic policy, tested under any discovery order, keeps plugins stable across build and deployment environment changes.