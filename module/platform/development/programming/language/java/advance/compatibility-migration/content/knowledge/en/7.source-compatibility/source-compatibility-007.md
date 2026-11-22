# Checked Exceptions and Changes to Exception-Handling Requirements

In Java, checked exceptions are an important part of a method's contract. When a library or module changes the list of exceptions declared in throws, consumer source code may have to change how it calls methods, catches errors, or implements interfaces. However, this change does not always prevent old bytecode from linking. To assess a migration accurately, distinguish source compatibility, binary compatibility, and behavioral compatibility.

For example, one library version has a load() method declaring IOException. In a later version, the provider adds SQLException. Consumers calling the method may have to add a catch block or declare the new exception. Yet the JVM does not use the throws clause to identify a method's linking signature. Thus, a previously compiled program can still link against the new library version, and then encounter the new exception at runtime without handling for it in the old code.

## 1. What Is a Checked Exception?

Java divides exceptions into two main groups based on how the compiler requires them to be handled:

- **Checked exceptions:** exceptions extending Throwable that are not RuntimeException or Error. Source code must catch them with try/catch or declare propagation with throws.
- **Unchecked exceptions:** RuntimeException, its subclasses, and Error. The compiler does not force callers to catch or declare these exceptions.

Example:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ConfigLoader {
    public String load(Path path) throws IOException {
        return Files.readString(path);
    }
}
~~~

IOException is a checked exception. Callers must handle or declare it:

~~~java
public void start() throws IOException {
    String config = new ConfigLoader().load(Path.of("app.properties"));
    initialize(config);
}
~~~

Or callers can catch and translate the error:

~~~java
public void start() {
    try {
        String config = new ConfigLoader().load(Path.of("app.properties"));
        initialize(config);
    } catch (IOException exception) {
        throw new IllegalStateException("Cannot load application configuration", exception);
    }
}
~~~

The compiler checks this requirement from declared exception types and expressions that can throw checked exceptions. The JVM does not enforce checked-exception rules when executing bytecode. This is a crucial distinction when changing APIs previously compiled by consumers.

## 2. The throws Clause Is Part of the Source Contract

The throws clause states which checked exceptions a method can propagate to callers. It tells consumers which error types need handling and lets the compiler check exception-handling flow.

Example:

~~~java
public Customer findById(String id) throws IOException {
    // Read data from a source that may produce I/O errors.
}
~~~

The contract is not merely a list of exception names. It also encompasses what conditions trigger an exception, whether the method lets the exception pass through or wraps it, the system state after an error, and whether callers can safely retry.

A method may declare throws IOException yet in practice only throw a subclass such as FileNotFoundException. Callers are allowed to rely on the declared IOException type; if the provider wants to commit to finer detail, it must clearly document the exception types and trigger conditions.

## 3. Compatibility Dimensions to Distinguish

### 3.1. Source Compatibility

A consumer is considered source-compatible when old source code still compiles against the new library version without edits due to the change under consideration.

Checked exception changes can force callers to:

- Add a catch block for the new checked exception type.
- Add the exception to the calling method's throws clause.
- Change exception types declared at higher API layers.
- Adjust interface or abstract method implementations.
- Modify lambda expressions or method references assigned to functional interfaces.

### 3.2. Binary Compatibility

Whether previously compiled consumer bytecode can continue linking against the new library version is a separate question. In a JVM method descriptor, the elements used to identify a method consist of method name, parameter types, and return type; the declared exception list is not part of the descriptor.

Therefore, merely adding, removing, or changing types in throws usually does not alter the method descriptor, and that change alone does not break binary linkage. However, if the method actually throws a new checked exception, old bytecode may lack a matching handler and the exception may propagate out of the call flow.

### 3.3. Behavioral Compatibility

Even when signatures and binary linkage remain unchanged, changing the actual exception type thrown, timing, trigger conditions, or post-error state can still cause consumers to behave differently.

For example, a caller previously caught IOException and retried on transient errors. The new version wraps all errors in IllegalStateException. The program may still compile and link, yet the caller's retry policy is no longer triggered.

Thus, evaluate all three dimensions rather than concluding “binary compatible” equals “safe to upgrade”.

## 4. Adding a Checked Exception to an Existing Method

Suppose the initial version declares:

~~~java
public Customer load(String id) throws IOException {
    return repository.load(id);
}
~~~

A consumer can write:

~~~java
Customer customer = service.load(customerId);
~~~

inside a method already declaring throws IOException, or catch IOException locally.

In a later version, the provider adds SQLException:

~~~java
public Customer load(String id) throws IOException, SQLException {
    return repository.load(id);
}
~~~

Recompiling consumers may receive an error like:

~~~text
unreported exception SQLException; must be caught or declared to be thrown
~~~

Callers must handle the new exception or propagate it further. This change can break source compatibility, especially for public APIs used by many modules.

Regarding binary compatibility, throws is not part of the method descriptor. Old bytecode can still resolve the same method if name, parameters, return type, and other linkage conditions remain unchanged. Yet if the new implementation actually throws SQLException, old code can let the exception escape without expected handling. The JVM does not automatically convert checked exceptions to unchecked ones nor inject catch blocks into old bytecode.

## 5. Widening or Changing Checked Exception Types

Changing from a specific type to a broader supertype usually hurts source compatibility because callers must prepare for more error categories.

Example:

~~~java
// Old version
public String read() throws FileNotFoundException;

// New version
public String read() throws IOException;
~~~

Old callers catching only FileNotFoundException may fail to handle other IOExceptions that the new version can throw. If the caller declares throws FileNotFoundException, it also cannot propagate the broader IOException. Callers must update catch or throws.

Another case is changing from IOException to Exception:

~~~java
// Before
public Data load() throws IOException;

// After
public Data load() throws Exception;
~~~

The Exception type is far broader. Consumers may have to modify multiple API layers, because intermediate methods that previously declared only IOException cannot naturally propagate every Exception.

If a new error cause must be added while keeping the contract stable, consider placing the new exception under an already-declared supertype, wrapping the cause in an existing exception, or creating a new method/API. Each option requires weighing how callers distinguish errors and retry policies.

## 6. Narrowing or Removing Checked Exceptions

Narrowing the checked exception list is not always completely free of source-compatibility impact.

For example, a method previously declared:

~~~java
public Customer load() throws IOException;
~~~

The new version declares only:

~~~java
public Customer load() throws FileNotFoundException;
~~~

Callers catching IOException remain valid because IOException is a superclass of FileNotFoundException. Callers declaring throws IOException can also still invoke the method. However, classes implementing an interface or overriding the method may need adjustments if they declare a broader checked exception than the new allowance.

If checked exceptions are removed altogether:

~~~java
public Customer load();
~~~

Some callers with a catch IOException block wrapping only this call may fail to recompile because that checked exception is no longer thrown inside the try block. Callers may also need to remove throws IOException declarations if no other operation requires it.

Removing checked exceptions can improve API ergonomics if the error no longer makes sense or is handled internally. Still, check how consumers use catch, throws, method references, and wrapper layers.

## 7. Checked Exception Rules for Overriding and Implementing Interfaces

Java restricts checked exceptions an overriding method may declare. An overriding method may declare the same type or a subtype of the checked exceptions on the parent/interface method; it must not widen to a broader checked exception.

Example:

~~~java
interface CustomerReader {
    Customer read() throws IOException;
}

class FileCustomerReader implements CustomerReader {
    @Override
    public Customer read() throws FileNotFoundException {
        // Valid: FileNotFoundException is a subclass of IOException.
        return loadFile();
    }
}
~~~

Invalid example:

~~~java
class RemoteCustomerReader implements CustomerReader {
    @Override
    public Customer read() throws IOException, SQLException {
        // Error: SQLException is not in the interface method's throws.
        return loadRemote();
    }
}
~~~

If SQLException must be raised, the implementation can wrap it in an IOException fitting the contract, handle it internally, or update the interface under a compatibility plan.

### 7.1. Widening throws on an Interface

Suppose an interface is widened from:

~~~java
interface CustomerReader {
    Customer read() throws IOException;
}
~~~

to:

~~~java
interface CustomerReader {
    Customer read() throws IOException, SQLException;
}
~~~

An existing implementation declaring only throws IOException can still implement the new interface because implementing methods are permitted to declare fewer checked exceptions. However, callers using the CustomerReader reference type must additionally handle SQLException upon recompilation.

### 7.2. Narrowing throws on an Interface

If the interface drops IOException, old implementations still declaring throws IOException may stop compiling because an overriding method cannot declare broader checked exceptions than the new method. This is why changing a throws clause can affect both callers and implementors in two opposite directions.

## 8. Checked Exceptions in Functional Interfaces, Lambdas, and Method References

A functional interface's throws clause affects which lambdas and method references consumers can assign to that interface.

Example:

~~~java
@FunctionalInterface
interface ConfigReader {
    String read() throws IOException;
}
~~~

A lambda can call an API throwing IOException:

~~~java
ConfigReader reader = () -> Files.readString(Path.of("app.properties"));
~~~

If the interface drops throws IOException, the lambda above stops compiling because the target method does not permit propagating that checked exception out.

Conversely, when an interface widens its throws clause, lambdas that throw no exceptions can keep working. Yet callers invoking reader.read() will have to handle the broader set of checked exceptions.

Method references follow the same rules. A method reference is compatible with a functional interface only if parameter types, return type, and throwable exceptions fit the functional interface's descriptor under Java's checking rules.

When changing the throws clause of an interface with many consumers, find all of:

- Lambda expressions assigned to the interface.
- Method references to methods throwing checked exceptions.
- Classes or anonymous classes implementing the interface.
- Callers invoking methods via the interface type.

## 9. Replacing Checked Exceptions with Unchecked Exceptions

Sometimes an API shifts from checked exceptions to unchecked exceptions:

~~~java
// Before
public Customer load(String id) throws IOException;

// After
public Customer load(String id);
~~~

If the new implementation throws UncheckedIOException or a RuntimeException, the compiler does not require callers to declare or catch it. However, an old consumer may have a catch IOException block dedicated solely to that call. Upon recompilation, that specific catch can become unreachable if no other call in the try block can throw IOException.

Furthermore, replacing checked exceptions with unchecked exceptions can alter how the application handles errors. Call layers that previously propagated IOException up to a boundary now see the exception pass through layers without declarations and get handled by the framework as a runtime error.

Do not switch to unchecked merely to shrink throws lists in signatures. Classify the nature of the error:

- Errors caused by invalid inputs or programming bugs often suit unchecked exceptions.
- I/O errors, external service failures, config reading errors, or resource failures usually need evaluation against business contracts and recoverability.
- If switching to unchecked, define exception types, causes, logging, retries, and the boundary responsible for handling.

## 10. Changing the Actual Exception Type While Keeping throws Unchanged

You can keep throws IOException unchanged yet alter the actual exception type thrown:

~~~java
// Old version
throw new FileNotFoundException("Customer file is missing");

// New version
throw new SocketException("Remote storage is unavailable");
~~~

Both are IOExceptions, so callers catching IOException remain type-compatible. However, callers may have specific logic for FileNotFoundException—for instance, showing a “file not found” message instead of retrying the connection. New behavior can change business decisions.

Similarly, changing exception wrapping can destroy error classification if the cause is not preserved. For example, wrapping SQLException in a generic exception without passing the cause loses diagnostic information.

A good exception contract should describe:

- Exception types that may be thrown.
- Conditions causing each exception type.
- Whether exceptions pass through verbatim or get wrapped.
- Whether causes are preserved.
- Whether callers can retry or must ask for user intervention.
- State of resources, transactions, or data after an error occurs.

## 11. Designing APIs for Safer Exception Evolution

### 11.1. Use Stable Domain Exceptions at Module Boundaries

If a library wants to swap database drivers or HTTP clients, avoid leaking implementation-specific exceptions directly across public APIs without good reason. Define exceptions belonging to the library's domain:

~~~java
public class CustomerAccessException extends Exception {
    public CustomerAccessException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

API:

~~~java
public interface CustomerLookup {
    Customer findById(String id) throws CustomerAccessException;
}
~~~

The implementation can translate errors from JDBC, HTTP, or caches into CustomerAccessException, preserving the cause for diagnostics. When swapping data access libraries, consumers do not depend on driver exceptions.

However, domain exceptions are useful only if they provide sufficiently clear categorization. If every error is collapsed into one type lacking error codes, subtypes, or appropriate causes, consumers may lose the ability to treat transient and permanent failures differently.

### 11.2. Keep Parent Exceptions Stable and Add Controlled Subtypes

If an API already declares throws IOException, you can add a new subtype of IOException to represent a specific cause. Callers catching IOException still receive the error; consumers needing special handling can catch the subtype when desired.

Do not narrow the declared type from parent class to subclass if doing so impacts implementing consumers or callers relying on the broader scope. Keep the old declared type and document concrete subtypes.

### 11.3. Use a New Method When Error Semantics Change Substantially

If a new method has a fundamentally different error model, one option is adding a new method with a clear contract, keeping the old method during transition, and marking it deprecated where appropriate.

Example:

~~~java
public Customer load(String id) throws IOException {
    return loadLegacy(id);
}

public Customer loadWithPolicy(String id) throws CustomerAccessException {
    return loadUsingDomainPolicy(id);
}
~~~

This is an illustrative example. New APIs need names expressing semantics clearly without creating two conflicting handling paths. When keeping the old method, documentation must specify the planned removal timeline and conversion steps.

### 11.4. Preserve Causes and Context

When wrapping exceptions, always consider passing the cause:

~~~java
try {
    return repository.load(id);
} catch (SQLException exception) {
    throw new CustomerAccessException(
            "Cannot load customer " + id,
            exception);
}
~~~

Do not place sensitive data such as tokens, passwords, or unnecessary personal information into messages. Exception messages frequently appear in logs and observability systems.

## 12. Evaluating throws Clause Changes During Migration

When preparing an API change, use the following matrix to identify what needs checking:

| Change | Source compatibility | Binary compatibility | Behavioral risk |
|---|---|---|---|
| Add new checked exception | Can break callers that must add catch/declare | Usually preserved because throws is not in the method descriptor | Old code may receive an unhandled exception. |
| Widen exception type from subtype to supertype | Callers and wrapper layers may require edits | Descriptor usually unchanged | Callers may encounter broader error types than expected. |
| Narrow exception type | Callers usually still handle it, yet implementors may need to adjust throws | Descriptor usually unchanged | Error classification and handling branches may change. |
| Remove checked exception | Specific catch blocks or old throws may stop compiling | Descriptor usually unchanged | Callers may no longer receive errors as before. |
| Change checked to unchecked | Specific checked catch blocks may become unreachable | Descriptor usually unchanged | Exceptions may bypass boundaries previously handling checked exceptions. |
| Keep throws yet swap actual exception | May still compile | Preserved if descriptor unchanged | Subtype catch logic, retries, and messaging may change. |

“Usually preserved” in the binary column applies solely to the throws change itself. If method names, parameters, return types, exception classes, visibility, or module boundaries change concurrently, independent binary incompatibilities can still arise.

## 13. Process for Checking Consumers Before Making Changes

### Step 1: List APIs With Checked Exceptions

List public/protected methods, interfaces, abstract classes, and functional interfaces declaring throws. For libraries, check both exception types appearing in public signatures and documented exceptions.

### Step 2: Locate Callers and Implementors

Find every place calling the method, catching exceptions, declaring throws, overriding methods, or implementing interfaces. Include tests, adapters, plugins, and separate source sets. Specifically locate lambdas and method references if the API is a functional interface.

### Step 3: Analyze Exception Hierarchy

Determine whether the new checked exception is a subtype of the previously declared type. Inspect whether callers catch specific classes or parent classes; inspect whether implementations declare broader exceptions than the overridden method.

### Step 4: Inspect Bytecode and API Metadata

Use javap -s -v to inspect method descriptors and Exceptions attributes. API compatibility tools can help detect declared exception changes in docs/API metadata, yet you must understand that throws is absent from JVM method descriptors.

Example:

~~~bash
javap -classpath library.jar -s -v com.example.CustomerService
~~~

In the output, the descriptor shows the name and parameter/return types in JVM format. The Exceptions attribute lists declared exceptions. Changes to Exceptions can impact source contracts and reflection metadata even when descriptors stay unchanged.

### Step 5: Run Consumer Compilation Tests

Recompile representative consumers against the new library version. Check callers, implementors, lambdas, method references, and wrapper APIs.

### Step 6: Run Binary Compatibility Tests

Keep a consumer compiled against the old library, then run it with the new library on the corresponding classpath/module path. Check linkage and observe actual exceptions. Do not check only whether the JVM starts up; exercise code paths capable of triggering the new exception.

### Step 7: Check Behavioral Contracts

Write tests for each error category, trigger condition, cause, post-error state, and retry policy. Confirm error-handling layers across the application still receive expected exception types without swallowing critical details.

### Step 8: Update Documentation and Roadmap

If the change is breaking at the source or behavioral level, state it clearly in release notes, migration guides, and versioning policies. If needed, supply a transitional release or new API before removing the old contract.

## 14. Comprehensive Example: Changing Exceptions in a Library

Suppose library version 1 declares:

~~~java
public interface ReportStore {
    Report load(String reportId) throws IOException;
}
~~~

A consumer application writes:

~~~java
public Report loadReport(String id) {
    try {
        return reportStore.load(id);
    } catch (FileNotFoundException exception) {
        return Report.empty();
    } catch (IOException exception) {
        throw new IllegalStateException("Cannot load report", exception);
    }
}
~~~

In version 2, the team wants to add remote service access errors and changes the declaration to:

~~~java
public interface ReportStore {
    Report load(String reportId) throws IOException, SQLException;
}
~~~

Points to consider:

1. Recompiling callers must handle or declare SQLException.
2. Existing implementations declaring only IOException can still implement the new interface, whereas a new implementation cannot additionally declare SQLException if the interface does not allow it; here the interface now permits it.
3. Old consumer bytecode can still link because the method descriptor did not change.
4. Old consumers may receive an unhandled SQLException if the new implementation throws that exception directly.
5. If SQLException is essentially an internal data-access error, consider wrapping it into a domain exception under IOException or defining a stable library exception.
6. Check retry policies: transient connection errors may be retried, whereas SQL errors due to invalid data or statements probably should not be retried.

Another option is keeping throws IOException unchanged and translating storage-adapter errors into IOException with SQLException as its cause. This preserves callers' source contract, yet you must assess whether collapsing errors removes consumers' ability to distinguish cases they need to handle.

## 15. Checklist When Changing Checked Exceptions

- [ ] Identified affected public APIs, interfaces, abstract methods, and functional interfaces.
- [ ] Distinguished checked exceptions from unchecked exceptions.
- [ ] Evaluated callers, catch clauses, throws propagation, overrides, and implementors.
- [ ] Checked lambda expressions and method references if applicable.
- [ ] Distinguished source compatibility, binary compatibility, and behavioral compatibility.
- [ ] Verified throws is not part of JVM method descriptors and checked metadata when needed.
- [ ] Preserved cause and context when wrapping exceptions.
- [ ] Identified retries, transactions, resource lifecycles, and post-error data state.
- [ ] Ran appropriate consumer compilation tests and binary compatibility tests.
- [ ] Tested actual exception types on the target JDK.
- [ ] Updated documentation, release notes, and migration guides.

## Conclusion

Checked exceptions are part of source contracts and error-handling behavior. Adding, widening, narrowing, or removing checked exceptions can impact callers, implementors, lambdas, and method references in different ways. The throws clause itself does not appear in JVM method descriptors, so declaration changes generally do not break binary linkage; however, old bytecode can still receive a new exception it was never built to handle. During migration, verify source, binary, and behavioral compatibility, inspect exception hierarchies, preserve cause details, test previously compiled consumers, and update release roadmaps so exception-contract changes remain predictable.
